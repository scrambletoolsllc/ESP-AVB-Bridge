#!/usr/bin/env python3
"""Exercise installed RPC routing with concurrent callers and late replies."""
from pathlib import Path
import argparse
import subprocess
import tempfile
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sanitizer', choices=('address', 'thread'), default='address')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
source = (root / 'managed_components/espressif__esp_hosted/host/drivers/rpc/core/rpc_core.c').read_text()
def function(signature):
    start = source.index(signature + '\n{')
    opened = source.index('{', start)
    depth = 1
    end = opened + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]
functions = '\n'.join(function(signature) for signature in (
    'static int set_sync_resp_sem(ctrl_cmd_t *app_req)',
    'static int post_sync_resp_sem(ctrl_cmd_t *app_resp)',
    'static ctrl_cmd_t *take_sync_response(ctrl_cmd_t *app_req)',
    'static ctrl_cmd_t * get_response(int *read_len, ctrl_cmd_t *app_req)'))
harness = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <semaphore.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MAX_SYNC_RPC_TRANSACTIONS 8
#define RPC_ID__Req_Base 100
#define RPC_ID__Resp_Base 200
#define RPC_ID__Resp_Max 300
#define CALLBACK_NOT_REGISTERED -2
#define CALLBACK_SET_SUCCESS 0
#define MSG_ID_OUT_OF_ORDER -3
#define SUCCESS 0
#define DEFAULT_RPC_RSP_TIMEOUT 1
#define portENTER_CRITICAL(lock) pthread_mutex_lock(lock)
#define portEXIT_CRITICAL(lock) pthread_mutex_unlock(lock)
static pthread_mutex_t sync_rsp_lock = PTHREAD_MUTEX_INITIALIZER;
typedef struct {
 uint32_t uid; int msg_id; void *rpc_rsp_cb, *rx_sem; int rsp_timeout_sec;
} ctrl_cmd_t;
typedef struct { uint32_t uid; void *sem; ctrl_cmd_t *response; } sync_rsp_t;
static sync_rsp_t sync_rsp_table[MAX_SYNC_RPC_TRANSACTIONS];
static void *create_sem(int maximum) {
 (void)maximum;
 sem_t *handle = malloc(sizeof(*handle)); assert(handle);
 assert(sem_init(handle, 0, 1) == 0); return handle;
}
static int get_sem(void *handle, int timeout) {
 assert(handle);
 if (!timeout) return sem_trywait(handle);
 struct timespec deadline; clock_gettime(CLOCK_REALTIME, &deadline);
 deadline.tv_sec += timeout;
 return sem_timedwait(handle, &deadline);
}
static int post_sem(void *handle) { assert(handle); return sem_post(handle); }
static int destroy_sem(void *handle) {
 assert(handle); assert(sem_destroy(handle) == 0); free(handle); return 0;
}
static struct operations {
 void *(*_h_create_semaphore)(int);
 int (*_h_get_semaphore)(void *, int);
 int (*_h_post_semaphore)(void *);
 int (*_h_destroy_semaphore)(void *);
} operations = {create_sem, get_sem, post_sem, destroy_sem};
static struct { struct operations *funcs; } g_h = {&operations};
'''
checks = r'''
static void *worker(void *opaque) {
 uintptr_t worker_id = (uintptr_t)opaque;
 for (unsigned iteration = 0; iteration < 10000; ++iteration) {
  ctrl_cmd_t request = {.uid = 100 + worker_id * 10000 + iteration, .msg_id = 101};
  ctrl_cmd_t response = {.uid = request.uid, .msg_id = 201};
  assert(set_sync_resp_sem(&request) == 0);
  sched_yield();
  assert(post_sync_resp_sem(&response) == 0);
  assert(post_sync_resp_sem(&response) == CALLBACK_NOT_REGISTERED);
  int length = 0;
  assert(get_response(&length, &request) == &response);
  assert(length == sizeof(response) && request.rx_sem == NULL);
  assert(post_sync_resp_sem(&response) == CALLBACK_NOT_REGISTERED);
 }
 return NULL;
}
static void *late_reply(void *opaque) {
 ctrl_cmd_t *response = opaque;
 sched_yield();
 int result = post_sync_resp_sem(response);
 assert(result == 0 || result == CALLBACK_NOT_REGISTERED);
 return NULL;
}
int main(void) {
 ctrl_cmd_t first = {.uid=1, .msg_id=101}, second = {.uid=2, .msg_id=102};
 ctrl_cmd_t first_reply = {.uid=1, .msg_id=201}, second_reply = {.uid=2, .msg_id=202};
 assert(set_sync_resp_sem(&first) == 0 && set_sync_resp_sem(&second) == 0);
 assert(post_sync_resp_sem(&second_reply) == 0);
 assert(post_sync_resp_sem(&first_reply) == 0);
 int length;
 assert(get_response(&length, &first) == &first_reply);
 assert(get_response(&length, &second) == &second_reply);
 pthread_t workers[4];
 for (uintptr_t index = 0; index < 4; ++index)
  assert(pthread_create(&workers[index], NULL, worker, (void *)index) == 0);
 for (unsigned index = 0; index < 4; ++index) pthread_join(workers[index], NULL);
 for (unsigned iteration = 0; iteration < 1000; ++iteration) {
  ctrl_cmd_t request = {.uid=50000+iteration, .msg_id=101};
  ctrl_cmd_t response = {.uid=request.uid, .msg_id=201};
  assert(set_sync_resp_sem(&request) == 0);
  pthread_t responder;
  assert(pthread_create(&responder, NULL, late_reply, &response) == 0);
  ctrl_cmd_t *received = take_sync_response(&request);
  assert(received == NULL || received == &response);
  pthread_join(responder, NULL);
  assert(post_sync_resp_sem(&response) == CALLBACK_NOT_REGISTERED);
 }
 for (unsigned index = 0; index < MAX_SYNC_RPC_TRANSACTIONS; ++index)
  assert(!sync_rsp_table[index].uid && !sync_rsp_table[index].sem && !sync_rsp_table[index].response);
 puts("RPC reverse-order, 40000 concurrent calls, duplicate, and 1000 timeout/reply races passed");
}
'''
with tempfile.TemporaryDirectory() as work:
 path = Path(work) / 'test.c'
 binary = Path(work) / 'test'
 path.write_text(harness + functions + checks)
 subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-pthread', '-fsanitize=' + ('address,undefined' if args.sanitizer == 'address' else 'thread'), '-g', str(path), '-o', str(binary)], check=True)
 subprocess.run([str(binary)], check=True)
