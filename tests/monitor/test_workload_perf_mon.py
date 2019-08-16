import calendar
from collections import deque
from datetime import datetime as dt
import unittest
import uuid
from unittest.mock import MagicMock

import numpy as np

from tests.utils import get_test_workload
from titus_isolate.event.constants import STATIC
from titus_isolate.monitor.cgroup_metrics_provider import CgroupMetricsProvider
from titus_isolate.monitor.cpu_usage import CpuUsage, CpuUsageSnapshot
from titus_isolate.monitor.mem_usage import MemUsage, MemUsageSnapshot
from titus_isolate.monitor.utils import normalize_data
from titus_isolate.monitor.workload_monitor_manager import DEFAULT_SAMPLE_FREQUENCY_SEC
from titus_isolate.monitor.workload_perf_mon import WorkloadPerformanceMonitor


class TestWorkloadPerfMon(unittest.TestCase):

    def test_single_sample(self):
        workload = get_test_workload(uuid.uuid4(), 2, STATIC)
        metrics_provider = CgroupMetricsProvider(workload)
        perf_mon = WorkloadPerformanceMonitor(metrics_provider, DEFAULT_SAMPLE_FREQUENCY_SEC)

        # Initial state should just be an empty timestamps buffer
        _, timestamps, buffers = perf_mon._get_cpu_buffers()
        self.assertEqual(0, len(buffers))
        self.assertEqual(0, len(timestamps))

        # Expect no change because no workload is really running and we haven't started mocking anything
        perf_mon.sample()
        _, timestamps, buffers = perf_mon._get_cpu_buffers()
        self.assertEqual(0, len(buffers))
        self.assertEqual(0, len(timestamps))

        # Mock reporting metrics
        cpu_usage = CpuUsage(pu_id=0, user=100, system=50)
        mem_usage = MemUsage(user=1000000)
        cpu_snapshot = CpuUsageSnapshot(timestamp=dt.now(), rows=[cpu_usage])
        mem_snapshot = MemUsageSnapshot(timestamp=dt.now(), usage=mem_usage)

        metrics_provider.get_cpu_usage = MagicMock(return_value=cpu_snapshot)
        metrics_provider.get_mem_usage = MagicMock(return_value=mem_snapshot)
        perf_mon.sample()

        _, timestamps, buffers = perf_mon._get_cpu_buffers()
        self.assertEqual(1, len(buffers))
        self.assertEqual(1, len(timestamps))

        buffer = buffers[cpu_usage.pu_id]
        self.assertEqual(1, len(buffer))
        self.assertEqual(cpu_usage.user + cpu_usage.system, buffer[0])

    def test_monitor_cpu_usage_normalization(self):
        to_ts = lambda d: calendar.timegm(d.timetuple())

        timestamps = deque(map(to_ts,
                               [dt(2019, 3, 5, 10, 13, 28),
                                dt(2019, 3, 5, 10, 14, 11),
                                dt(2019, 3, 5, 10, 14, 30)]))

        data = normalize_data(
            timestamps,
            [deque([100, 200, 200], 100),
             deque([50, 300, 360], 100)])

        # Last data bucket
        expected_processing_time = (360-300 + 200-200)
        expected_duration_ns = (timestamps[-1] - timestamps[-2]) * 1000000000
        expected_usage = expected_processing_time / expected_duration_ns
        self.assertAlmostEqual(expected_usage, data[-1])

        # Penultimate bucket
        expected_processing_time = (300-50 + 200-100)
        expected_duration_ns = (timestamps[-2] - timestamps[-3]) * 1000000000
        expected_usage = expected_processing_time / expected_duration_ns
        self.assertAlmostEqual(expected_usage, data[-2])

        self.assertEqual(58, np.sum(np.isnan(data).astype(np.int16)))

        try:
            normalize_data(
                deque([]),
                [deque([]), deque([])])
        except:
            self.fail("Should not raise on empty data.")
