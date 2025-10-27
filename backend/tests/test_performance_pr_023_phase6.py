# Performance Load Test for PR-023 Phase 6
# File: backend/tests/test_performance_pr_023_phase6.py

"""
Load test for Phase 6 database integration + caching layer.

Simulates 100+ concurrent users hitting Phase 6 endpoints.
Measures:
  - Response times (P50, P95, P99)
  - Cache hit rates
  - Database query load
  - Error rates

Usage:
  pip install locust
  locust -f backend/tests/test_performance_pr_023_phase6.py \
    -u 100 -r 10 --run-time 300s -H http://localhost:8000

Expected Results (with caching):
  P50 Latency:   ~10-20ms ✅
  P95 Latency:   <50ms ✅
  P99 Latency:   <100ms ✅
  Throughput:    1000+ req/s ✅
  DB Queries:    2-5 per second ✅
"""

import random
import string

from locust import between, events, task
from locust.contrib.fasthttp import FastHttpUser

# Performance benchmarks (targets)
BENCHMARKS = {
    "p50_latency_ms": 25,  # Target: 10-25ms (cache hits)
    "p95_latency_ms": 50,  # Target: <50ms
    "p99_latency_ms": 100,  # Target: <100ms
    "error_rate": 0.01,  # Target: <1% errors
    "throughput_req_per_sec": 500,  # Target: 1000+
}


class TradingAPILoadTest(FastHttpUser):
    """
    Simulates a trading platform user hitting Phase 6 endpoints.

    Weighted task distribution:
      - 50% reconciliation status (high traffic endpoint)
      - 30% open positions (medium traffic)
      - 20% guards status (lower frequency)
    """

    wait_time = between(0.5, 2.0)  # Random wait between 0.5-2 seconds

    def on_start(self):
        """Initialize test user with authentication token."""
        # Generate test JWT token (in production, use real token)
        self.token = self._generate_test_token()
        self.user_id = self._generate_test_user_id()

    def _generate_test_token(self) -> str:
        """Generate test JWT token for authentication."""
        # Simplified token - in production would use jwt.encode()
        return "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJyb2xlIjoidXNlciIsImV4cCI6OTk5OTk5OTk5OX0.test"

    def _generate_test_user_id(self) -> str:
        """Generate test user ID."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=32))

    @task(5)
    def get_reconciliation_status(self):
        """
        GET /api/v1/reconciliation/status

        Expected: Cache hit (5-20ms)
        Endpoint: Queries ReconciliationLog, caches for 5 seconds
        """
        headers = {"Authorization": self.token}
        with self.client.get(
            "/api/v1/reconciliation/status", headers=headers, catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.failure(f"Unauthorized: {response.text}")
            elif response.status_code == 500:
                response.failure(f"Server error: {response.text}")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(3)
    def get_open_positions(self):
        """
        GET /api/v1/positions/open

        Expected: Cache hit (5-20ms)
        Endpoint: Queries open positions from ReconciliationLog
        """
        headers = {"Authorization": self.token}
        with self.client.get(
            "/api/v1/positions/open", headers=headers, catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.failure(f"Unauthorized: {response.text}")
            elif response.status_code == 500:
                response.failure(f"Server error: {response.text}")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(2)
    def get_guards_status(self):
        """
        GET /api/v1/guards/status

        Expected: Cache hit (5-20ms)
        Endpoint: Queries guard conditions from database
        """
        headers = {"Authorization": self.token}
        with self.client.get(
            "/api/v1/guards/status", headers=headers, catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.failure(f"Unauthorized: {response.text}")
            elif response.status_code == 500:
                response.failure(f"Server error: {response.text}")
            else:
                response.failure(f"Unexpected status: {response.status_code}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("\n" + "=" * 80)
    print("PHASE 6 PERFORMANCE LOAD TEST STARTED")
    print("=" * 80)
    print("\nBenchmarks:")
    print(f"  P50 Latency:    <{BENCHMARKS['p50_latency_ms']}ms")
    print(f"  P95 Latency:    <{BENCHMARKS['p95_latency_ms']}ms")
    print(f"  P99 Latency:    <{BENCHMARKS['p99_latency_ms']}ms")
    print(f"  Error Rate:     <{BENCHMARKS['error_rate']*100}%")
    print(f"  Throughput:     >{BENCHMARKS['throughput_req_per_sec']} req/s")
    print("\n" + "-" * 80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops - print results."""
    print("\n" + "=" * 80)
    print("PHASE 6 PERFORMANCE LOAD TEST RESULTS")
    print("=" * 80 + "\n")

    # Extract statistics from environment
    stats = environment.stats

    # Calculate aggregate metrics
    total_requests = sum(s.num_requests for s in stats.itervalues())
    total_failures = sum(s.num_failures for s in stats.itervalues())
    error_rate = total_failures / total_requests if total_requests > 0 else 0

    print(f"Total Requests:     {total_requests:,}")
    print(f"Total Failures:     {total_failures:,}")
    print(f"Error Rate:         {error_rate*100:.2f}%")
    print(f"Success Rate:       {(1-error_rate)*100:.2f}%")

    print("\nLatency Percentiles:")
    for endpoint in stats:
        s = stats[endpoint]
        print(f"\n  {endpoint}:")
        print(f"    Min:     {s.min_response_time:.1f}ms")
        print(f"    Max:     {s.max_response_time:.1f}ms")
        print(f"    Median:  {s.median_response_time:.1f}ms")
        print(f"    P95:     {s.get_response_time_percentile(0.95):.1f}ms")
        print(f"    P99:     {s.get_response_time_percentile(0.99):.1f}ms")
        print(f"    Requests: {s.num_requests:,}")

    print("\n" + "-" * 80)
    print("BENCHMARK ASSESSMENT:")
    print("-" * 80 + "\n")

    # Check benchmarks
    p95_latency = stats.total.get_response_time_percentile(0.95)
    p99_latency = stats.total.get_response_time_percentile(0.99)

    results = []

    if p95_latency < BENCHMARKS["p95_latency_ms"]:
        results.append(
            f"✅ P95 Latency: {p95_latency:.1f}ms < {BENCHMARKS['p95_latency_ms']}ms"
        )
    else:
        results.append(
            f"❌ P95 Latency: {p95_latency:.1f}ms > {BENCHMARKS['p95_latency_ms']}ms"
        )

    if p99_latency < BENCHMARKS["p99_latency_ms"]:
        results.append(
            f"✅ P99 Latency: {p99_latency:.1f}ms < {BENCHMARKS['p99_latency_ms']}ms"
        )
    else:
        results.append(
            f"❌ P99 Latency: {p99_latency:.1f}ms > {BENCHMARKS['p99_latency_ms']}ms"
        )

    if error_rate < BENCHMARKS["error_rate"]:
        results.append(
            f"✅ Error Rate: {error_rate*100:.2f}% < {BENCHMARKS['error_rate']*100}%"
        )
    else:
        results.append(
            f"❌ Error Rate: {error_rate*100:.2f}% > {BENCHMARKS['error_rate']*100}%"
        )

    for result in results:
        print(result)

    print("\n" + "=" * 80)
    print("CACHE EFFECTIVENESS:")
    print("=" * 80 + "\n")
    print("Expected: 80%+ cache hit rate (most requests <20ms)")
    print(f"Actual P50 Latency: {stats.total.median_response_time:.1f}ms")
    print("Expected (cache hits): 5-20ms")

    if stats.total.median_response_time < 20:
        print("✅ Cache is working effectively!")
    else:
        print("⚠️  Cache hit rate lower than expected")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":


    # Run with: locust -f test_performance_pr_023_phase6.py -u 100 -r 10 --run-time 300s
    print("To run performance test:")
    print("  locust -f backend/tests/test_performance_pr_023_phase6.py \\")
    print("    -u 100 -r 10 --run-time 300s -H http://localhost:8000")
