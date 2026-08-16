# Visual QC policy governance

## Safety status

The bundled catalog is temporarily `APPROVED` with approval scope
`DEMO_BASELINE_ONLY`. This simulated internal approval supports baseline demos
and workflow validation, but it is not production release authority or a
substitute for a plant control plan, cosmetic standard, engineering drawing,
or repair instruction.

Public standards define terminology, assessment frameworks, and quality-system
controls. They do not publish the OEM-specific scratch, dent, paint, weld,
or repair acceptance limits needed to release a production vehicle.

## Controlled source register

| Source | Publicly supported scope | Explicit limitation in this project |
| --- | --- | --- |
| ISO 4628-1:2016 | Designation of coating defect quantity, size, and appearance change | Does not become an OEM cosmetic acceptance limit |
| ISO 1101:2017 | Language and interpretation of geometrical tolerancing | Actual limits must come from an approved drawing |
| ISO 17637:2016 | Visual testing of fusion-welded joints | Weld-process applicability must be confirmed |
| ISO 5817:2023 | Quality levels B/C/D for covered fusion-weld imperfections | No default level is assigned; it is not a spot-weld acceptance rule |
| ISO 3779:2009 | VIN content and structure | Market and build-record checks remain required |
| ISO 9001:2015 | Documented information, control, evaluation, and improvement | Does not supply product acceptance limits |
| AIAG CQI-8 | Layered process audit governance and effectiveness | Licensed detail must be supplied by the organization |

Source links are stored in `agent/policies/qc_policy_catalog.json` and returned
by `GET /api/policies`.

## Decision authority

1. The model supplies evidence: class, confidence, bounding box, and mask.
2. LangGraph decides whether the evidence is confirmed, requires verification,
   or must stop at HITL.
3. The policy engine selects only a controlled action code and identifies
   missing evidence.
4. Groq may explain that immutable result. It cannot change the action, final
   status, test-drive gate, references, or measurements.
5. A catalog that is not `APPROVED`, or a decision with missing evidence, has
   `production_eligible=false`.
6. Production release requires an approved plant policy and accountable QC
   sign-off.

## Plant approval checklist

Before changing approval scope from `DEMO_BASELINE_ONLY` to `PRODUCTION`,
Quality Engineering must attach:

- OEM cosmetic acceptance standard by model and visual zone;
- released drawings and GD&T limits;
- approved repair restrictions;
- weld process and acceptance-level mapping;
- stud/nut BOM, presence/count, torque, and rework requirements;
- VIN market/build-record validation rules;
- work instructions with revision and effective date;
- role/authority matrix for PASS, HOLD, concession, and release;
- validation evidence showing that each encoded rule matches the controlled source.

## Groq reasoning configuration

Create a project-specific key in the Groq Console. Never place it in frontend
code or commit it to Git.

```dotenv
QC_REASONING_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-20b
```

If the key is missing, the API fails safely to deterministic reasoning. If a
Groq response is invalid or cites a source outside the policy context, that
response is rejected and the deterministic explanation is used.
