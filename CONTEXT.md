# Mailroom Classification

Prototype that reads the first-page scan of a bank mailroom item and proposes where it should be routed, for a human QC reviewer to confirm or correct.

## Language

**Scan**:
The first-page image submitted for classification.
_Avoid_: Document, letter, file, image

**Mail item**:
The physical letter the scan was taken from.
_Avoid_: Document, letter

**Proposal**:
The three predicted routings (branch, department, recipient), each with a confidence.
_Avoid_: Prediction, result, classification

**Correction**:
A QC reviewer's per-field fix to the proposal, held in UI state only.
_Avoid_: Edit, override, label

**QC tier**:
Urgency of human review. Tier 0 means look first (escape chosen or invalid combination); tier 1 means queue normally by lowest confidence.
_Avoid_: Priority, flag, score

**Escape**:
An explicit model opt-out, phrased as a sentence the reviewer can read: "branch cannot be determined from this page", "none of the listed departments fits", "recipient missing or not one of the listed people". Any escape forces QC tier 0.
_Avoid_: Fallback, default, unknown

**Routing options**:
The branch, department and recipient lists used for one session, editable by the reviewer in the sidebar as one plain name per line. The name is both the model's answer and what the reviewer sees. Defaults come from the hardcoded lists in `config`; edits are not persisted.
_Avoid_: Options, settings, catalogue
