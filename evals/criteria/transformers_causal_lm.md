# Transformers causal-LM forward census rubric

This is a source-grounded, read-only evaluation. The answer must make its
claims about the checked-out Transformers repository, not about a model's
general knowledge of Transformers.

| Criterion | Points | A strong answer |
| --- | ---: | --- |
| Scope and coverage | 0–3 | Covers both requested name families, accounts for inherited `forward()` methods, and reports counts plus only material exceptions. |
| Source-grounded evidence | 0–3 | Cites concrete `src/...:line` or `src/...:start-end` locations for representative classifications and exceptions. Claims agree with the supplied snippets. |
| Technical classification | 0–3 | Correctly distinguishes loss calculated directly in `forward`, target shifting in `forward`, and delegation to a `loss_function` helper. It avoids treating unrelated imports or comments as proof. |
| Useful synthesis | 0–1 | Identifies relevant `GenerationMixin` classes outside the requested naming pattern and presents a compact, decision-useful result. |

Pass at **7/10 or higher**, with at least **1 point** in both source-grounded
evidence and technical classification. A response with no usable source
citations cannot pass.
