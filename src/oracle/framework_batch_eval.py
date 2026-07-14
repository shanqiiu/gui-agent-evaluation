import os
import threading
import time

from GUI_TestFramework_v1 import scripts
from oracle_service import run_sequence


class OracleBatchEvaluator(object):

    def __init__(self, config: scripts.Config = None):
        self.config = config
        self.benchmark_dir = self.config.benchmark_dir
        self.max_workers = self.config.max_workers
        self.max_samples = self.config.max_samples
        self.threading_lock = threading.Lock()

        self.samples_dir_list = []
        samples = os.listdir(self.benchmark_dir)
        for sample in samples[:self.max_samples] if self.max_samples != -1 else samples:
            self.samples_dir_list.append(os.path.join(self.benchmark_dir, sample))

        self.total_samples = len(self.samples_dir_list)
        self.worker_speed_curve = []

    @staticmethod
    def run_single_sequence_bench(single_seq_bench_config=None):
        saved_path = os.path.join(
            single_seq_bench_config.data.OUTPUT_DIR,
            f"{os.path.basename(single_seq_bench_config.data.DATA_DIR)}.json",
        )
        if os.path.exists(saved_path):
            print(f"path: {saved_path} already exists, skip this task!")
            return

        print(f"running single sequence bench-test from: {single_seq_bench_config.data.DATA_DIR}...")
        try:
            run_sequence(single_seq_bench_config)
        except Exception as e:
            print(str(e))
        print(f"single sequence bench-test finished[from: {single_seq_bench_config.data.DATA_DIR}]")

    def _worker(self):
        while len(self.samples_dir_list) > 0:
            worker_start_time = time.time()
            self.threading_lock.acquire()
            try:
                this_sample_dir = self.samples_dir_list.pop()
            except Exception:
                self.threading_lock.release()
                return
            self.threading_lock.release()

            single_bench_config = scripts.Config()
            single_bench_config.data.DATA_DIR = this_sample_dir
            self.run_single_sequence_bench(single_seq_bench_config=single_bench_config)

            self.threading_lock.acquire()
            self.worker_speed_curve.append(time.time() - worker_start_time)
            self.threading_lock.release()

    def supervisor_worker(self):
        task_start_time = time.time()
        samples_dir_list_count = len(self.samples_dir_list)
        while len(self.samples_dir_list) > 0:
            cur_samples_dir_list_count = len(self.samples_dir_list)

            if cur_samples_dir_list_count < samples_dir_list_count:
                samples_dir_list_count = cur_samples_dir_list_count
                task_time_used = round((time.time() - task_start_time) / 3600, 6)

                if self.worker_speed_curve:
                    this_window_speed_curve = self.worker_speed_curve[-self.max_workers:]
                    speed = sum(this_window_speed_curve) / (len(this_window_speed_curve) * self.max_workers)
                else:
                    speed = 1e6

                eta = round(len(self.samples_dir_list) * speed / 3600, 6)
                finished = self.total_samples - len(self.samples_dir_list)
                print(
                    f"Process: [{finished}/{self.total_samples}], speed: {round(speed, 6)}s/sample, "
                    f"time used: {task_time_used}h, ETA: {eta}h"
                )
            time.sleep(0.1)

    def batch_evaluate(self):
        print(f"starting batch evaluate..., sliding_mode: [{self.config.sliding_mode}]")
        threading_list = []

        for _ in range(self.max_workers):
            threading_list.append(
                threading.Thread(target=self._worker, args=(), daemon=True)
            )

        threading_list.append(
            threading.Thread(target=self.supervisor_worker, args=(), daemon=True)
        )

        for p in threading_list:
            p.start()

        for p in threading_list:
            p.join()


if __name__ == "__main__":
    config_main = scripts.Config()
    oracle_batch_evaluator = OracleBatchEvaluator(config=config_main)
    oracle_batch_evaluator.batch_evaluate()
    print("\n所有测试完成")
