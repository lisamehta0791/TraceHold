# Benchmark results

Generated 2026-10-15T20:05:15. Identical SQL on both engines, one transaction per analysis step. The first run of each workload is reported as cold; median/min/max are over the remaining (warm) runs. Synthetic data only. Only these workloads were measured; no general claim is made.

Hardware: 11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz, 7.7 GB RAM, 8 logical CPUs. Both databases run in Docker Desktop (WSL2) on this machine with a 4 GB memory limit each.

Versions: {'Exasol': '2026.2.0-nano.3'}

| Engine | Tier | Workload | Transactions | Cold (s) | Median warm (s) | Min–max (s) | Runs |
|---|---|---|---:|---:|---:|---:|---:|
| Exasol | S | LOAD | 241,125 | 15.263 | 15.263 | 15.263–15.263 | 1 |
| Exasol | S | W2 | 241,125 | 30.281 | 27.845 | 23.329–32.361 | 3 |
| Exasol | S | W3 | 241,125 | 0.492 | 0.341 | 0.312–0.493 | 5 |
| Exasol | S | W1 | 241,125 | 4.776 | 4.999 | 4.893–5.877 | 5 |
| Exasol | M | LOAD | 958,023 | 19.294 | 19.294 | 19.294–19.294 | 1 |
| Exasol | M | W2 | 958,023 | 44.163 | 43.806 | 36.901–50.711 | 3 |
| Exasol | M | W3 | 958,023 | 0.46 | 0.572 | 0.435–0.795 | 5 |
| Exasol | M | W1 | 958,023 | 9.538 | 10.606 | 6.378–11.4 | 5 |
