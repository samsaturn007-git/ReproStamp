# PRD-09 app generation evaluation

The paired experiment used Field Notes and Studio Requests with fixture seed 42 and one attempt per fixture and arm. The single-stage arm asked for one typed patch. The plan-and-review arm used one planner/reviewer for task classification and final review, with a separate generator between them. Both arms had a combined output limit of 512 tokens per attempt. [Fixture manifest](../examples/app/evaluation.json)

The fixed oracle ran API health, task CRUD, browser task lifecycle, exact status order, and requested presentation. The runner also required TypeScript compilation, a production build, and three Python unit and whitespace checks before the app could serve. Runs used the pinned Linux ARM64 image with Chromium 159.0.8154.6, Firefox 159.0, and WebKit 27.2. The golden provider returned a scripted wrong empty-state message for one fixture so the oracle could grade a real assertion failure.

## Scripted results

| Arm | Passed / N | Attempts | Calls | Request bytes | Summed wall seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single stage | 1 / 2 | 2 | 2 | 5,779 | 62.03 |
| Plan and review | 2 / 2 | 2 | 6 | 13,489 | 46.07 |

The single-stage Studio Requests draft failed the empty-state assertion in all three engines. The scripted review corrected the message, and all three engines passed. The deterministic provider reports bytes, with no token counts or billed API cost. The scripted behavior was chosen to test that the oracle distinguishes passing and failing outputs. [Golden report](../.reprostamp/prd09-gates-8gj2e_ly/benchmark/report.md) · [Raw golden results](../.reprostamp/prd09-gates-8gj2e_ly/benchmark/report.json)

## Experimental results

The live run used Ollama with `qwen2.5-coder:3b` for generation and `qwen2.5-coder:1.5b` for planning and review. Billed API cost was USD 0. Local compute and energy costs were unmeasured.

| Arm | Passed / N | Attempts | Calls | Input tokens | Output tokens | Summed wall seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Single stage | 0 / 2 | 2 | 2 | 1,514 | 189 | 211.51 |
| Plan and review | 1 / 2 | 2 | 6 | 3,593 | 442 | 182.53 |

Field Notes passed after planning and review. In the single-stage trial, Chromium exceeded the startup window while Firefox and WebKit caught the extra status label. Both Studio Requests outputs added an extra status label and task fields. The browser and API checks caught these differences in all three engines. Each arm used one live attempt per fixture, and other checks were running during part of the live benchmark. The timings reflect those conditions. Repeated trials would be needed to estimate model variance or make a stable speed comparison. [Live report](../.reprostamp/prd09-final-live-sOMXdS/results/report.md) · [Raw live results](../.reprostamp/prd09-final-live-sOMXdS/results/report.json)

## Context selection

The index tracks file digests and symbols. The planner and reviewed diagnostic text can change which two source files are selected. In the exit gate, rebuilding the index with identical files reused all four entries. Changing one stylesheet rebuilt one entry, and a diagnostic naming that stylesheet ranked it first.

In the live trials, selected context used 2,048–2,235 bytes against 15,438–15,442 bytes for the same eligible files in full. Selection found one of the two target files in each trial and missed the stylesheet. The generated trial tables include the selected and full-source byte counts and target file coverage. Provider token totals include instructions and all calls that reported usage. The context comparison measures request size and retrieval coverage. Assessing the effect on output quality would require running a separate full-context arm.

## Reproduce the runs

```sh
reprostamp starter prepare --cache .reprostamp/app-cache
reprostamp app benchmark --suite examples/app/evaluation.json \\
  --cache .reprostamp/app-cache --out .reprostamp/app-evaluation
```

For the experimental run, add `--ollama-model qwen2.5-coder:3b --planner-model qwen2.5-coder:1.5b`, use a fresh output path, and repeat the preview command with its approval digest. Reports record all trials in JSON, including failures and provider usage where reported. The Markdown report links each trial to its executable evidence. [CLI walkthrough](../README.md#run-the-paired-evaluation)
