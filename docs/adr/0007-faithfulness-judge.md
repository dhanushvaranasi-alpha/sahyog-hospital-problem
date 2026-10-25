# ADR 0007 — Faithfulness judge: ragas on GPT-6 Luna, calibrated before use

```yaml
title: W2 answers are scored for faithfulness by ragas 0.4.3 running on GPT-6 Luna, after calibration on 20 answers
context: The p16 target is faithfulness of at least 0.9 by a calibrated judge (decision 18). ragas 0.4.3 failed to import with the resolved langchain-community 0.4.2, which no longer has the chat_models.vertexai module ragas imports. Run as written, the judge also counted the answer's required closing line ("your doctor will go through this with you") as an unsupported claim, because no report contains it.
options:
  - name: In-house judge using the same claim-by-claim method
    cost: About 60 lines on our ModelClient; drops the library the pack names
  - name: ragas with langchain-community pinned to 0.4.1
    cost: One extra pin; ragas calls the model through its own client, so spend is recorded by an httpx hook into the same ledger and budget check
  - name: Judge on the answer model (Claude Haiku 5.5)
    cost: Same provider as the answers it grades; on calibration it also flagged plain-word explanations ("heart scan", "patent means open") as unsupported
decision: ragas 0.4.3 with langchain-community pinned to 0.4.1 (chosen by Dhanush over the in-house judge), on GPT-6 Luna (chosen by Dhanush; a different provider from the answer model), with the fixed doctor hand-off clause removed before judging. An answer is faithful only at a score of 1.0. Revisit if a re-calibration shows more than 2 of 20 disagreements, or when ragas or langchain-community change.
consequences: Calibration set of 20 answers to new questions (evals/judge): 14 as generated, 6 deliberately altered (number, drug, reversed finding, added claim). Two judges were run; Dhanush reviewed G01 and the 3 items on which they disagreed (G11, G14, G15); the other items take the planted label. Result: Luna 20/20 agreement (7 unfaithful caught, including one real date error in an unaltered answer, 0 missed, 0 correct answers flagged); Haiku 17/20, which fails the rule. All model calls for this work (calibration answers, both judges, the judged W2 run) cost US$0.043.
versions_pinned: ragas == 0.4.3; langchain-community == 0.4.1; instructor == 1.17.0 (resolved); judge model openai/gpt-6-luna
checked_on: 2026-10-25
status: accepted (implements decision 18)
```

Limits stated plainly: the human graded 4 of the 20 items, chosen where the judges disagreed, not all 20. The 16 others rest on the planted labels, and an unaltered answer can still be wrong, as G14 showed.
