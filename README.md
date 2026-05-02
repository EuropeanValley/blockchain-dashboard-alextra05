# CryptoChain Analyzer Dashboard

Bitcoin blockchain analysis dashboard built with Python and Streamlit.

---

## Student Information

| Field | Value |
|---|---|
| Student Name | Alex Trapero Lopez |
| GitHub Username | alextra05 |
| Project Title | CryptoChain Analyzer Dashboard |
| Chosen AI Approach | Statistical Exponential Distribution Anomaly Detector (M4) |

---

## Module Tracking

| Module | What it should include | Status |
|---|---|---|
| M1 | Proof of Work Monitor | Done |
| M2 | Block Header Analyzer | Done |
| M3 | Difficulty History | Done |
| M4 | AI Component | Done |
| M5 | Merkle Proof Verifier | Done |
| M6 | Security Score | Done |

---

## Current Progress

- All four required modules (M1–M4) fully implemented and integrated in a tabbed Streamlit dashboard.
- M1 displays live difficulty, leading zero bits derived from the `bits` field, inter-block time histogram with exponential PDF overlay, and estimated network hash rate.
- M2 fetches the raw 80-byte block header, parses all 6 fields with correct little-endian handling, manually verifies SHA-256d Proof-of-Work using `hashlib`, and counts leading zero bits.
- M3 plots difficulty evolution over time, marks each 2016-block adjustment epoch, and shows actual vs target block time ratios.
- M4 runs a statistical anomaly detector on the last 200 inter-block times using the Exponential distribution as baseline, with metrics, scatter plot, and anomaly summary table.
- M5 (optional) Merkle Proof Verifier fully implemented — builds the full Merkle tree, generates and verifies proofs step by step with SHA-256d.
- M6 (optional) Security Score fully implemented — estimates 51% attack cost in USD/hour from live hash rate, and visualises confirmation depth vs attack probability using the Nakamoto 2008 formula.
- Dashboard auto-refreshes every 60 seconds and handles API errors gracefully without crashing.
- Final report added to `report/report.pdf`.

---

## Next Step

- Project complete and ready for final submission.

---

## Main Problem or Blocker

- None.

---

## How to Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Project Structure

```text
blockchain-dashboard-alextra05/
|-- README.md
|-- requirements.txt
|-- .gitignore
|-- app.py
|-- api/
|   `-- blockchain_client.py
|-- modules/
|   |-- m1_pow_monitor.py
|   |-- m2_block_header.py
|   |-- m3_difficulty_history.py
|   |-- m4_ai_component.py
|   |-- m5_merkle_proof.py
|   `-- m6_security_score.py
|-- tests/
|   `-- test_dashboard.py
`-- report/
    `-- report.pdf
```

<!-- student-repo-auditor:teacher-feedback:start -->
## Teacher Feedback

### Kick-off Review

Review time: 2026-04-20 13:55 CEST
Status: Green

Strength:
- Your repository keeps the expected classroom structure.

Improve now:
- The code should connect the API output to theory, especially leading zeros and bits or target.

Next step:
- Add two short code comments that explain leading zeros and the meaning of bits or target.

### Checkpoint Review

Review time: 2026-04-29 20:31 CEST
Status: Green

Strength:
- I can see the dashboard structure integrating the checkpoint modules.

Improve now:
- The checkpoint evidence is strong: the dashboard and core modules are visibly progressing.

Next step:
- Keep building on this checkpoint and prepare the final AI integration.
<!-- student-repo-auditor:teacher-feedback:end -->