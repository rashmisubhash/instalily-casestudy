# Evaluation Report

Generated: `2026-02-20T11:30:33.847365+00:00`  
Backend: `http://127.0.0.1:8000`

## Required Prompt Results

- Total: **3**
- Passed: **3**
- Pass rate: **100.0%**
- Latency p50: **2.43 ms**
- Latency p95: **2653.86 ms**

| Case | Type | Latency (ms) | Pass | Notes |
|---|---:|---:|---:|---|
| Install by Part ID | `part_lookup` | 2653.86 | yes | ok |
| Compatibility Check | `clarification_needed` | 2.43 | yes | ok |
| Symptom Troubleshooting | `model_required` | 1.98 | yes | ok |

## Edge Prompt Results

- Total: **10**
- Passed: **10**
- Pass rate: **100.0%**
- Latency p50: **1.77 ms**
- Latency p95: **2450.16 ms**

| Case | Type | Latency (ms) | Pass | Notes |
|---|---:|---:|---:|---|
| Out of Scope Oven | `clarification_needed` | 1.6 | yes | ok |
| Noisy Dishwasher | `model_required` | 1.6 | yes | ok |
| Model Only | `issue_required` | 1.64 | yes | ok |
| Part Only | `part_lookup` | 2450.16 | yes | ok |
| Garbage Input | `clarification_needed` | 1.75 | yes | ok |
| Broken Fridge Water | `model_required` | 1.78 | yes | ok |
| Follow-up Language | `model_required` | 1.86 | yes | ok |
| Compatibility Unknown Model | `compatibility` | 134.1 | yes | ok |
| Short Symptom | `model_required` | 2.09 | yes | ok |
| Washer Out of Scope | `clarification_needed` | 1.54 | yes | ok |
