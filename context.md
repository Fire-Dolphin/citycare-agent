# Context for the agentcore assignment

Read this before you write any code. Point Claude Code at it too.

## 1. What we're building

We build AI agents that run the front desk of Indian hospitals. Patients message the hospital on WhatsApp (later, they'll call too), and agents book appointments, chase bills, answer questions, and hand over to staff when needed. One hospital can have hundreds of these conversations at the same time, and some of them are about people who are unwell, so the agents must be safe, predictable and cheap.

The engine under all of this is an **agent runtime**: the loop that calls the model, runs tools, enforces rules, and records what happened. That's what you're building, as a package called `agentcore`, plus a small team of agents on top of it for one fictional hospital, City Care Hospital in Pune.

## 2. What we want from you

```
   patient message  (POST /chat: session_id, phone, message)
          |
          v
   emergency check  ---- emergency? ---->  safety reply (108), emergency: true
          |
          v
   router (claude-haiku-5-5)  ---- picks one ---->  booking | billing | info | human
          |
          v
   specialist agent, running on agentcore:
      loop -> model -> tool call -> [before-tool hooks] -> tool -> [after-tool hooks] -> model ...
          |
          v
   hospital system (mock_hospital, slow and unreliable)
```

- `agentcore/` knows nothing about hospitals. No hospital imports in it. We'll check.
- Agents, tools, prompts and hospital rules live outside it (for example in `agent_service/`).
- Every safety rule in section 5 that can be enforced in code, must be (in hooks or tools). Prompts help the model behave; code makes sure it does.

The full list of must-haves is in the assignment brief. This file explains the world they live in.

## 3. The /chat contract

`agent_service/schemas.py` defines it. The eval runner depends on it, so keep these fields:

| Field | Meaning |
|---|---|
| `session_id` (in) | One WhatsApp conversation |
| `phone` (in) | The patient's WhatsApp number, already verified by WhatsApp. **This is who the patient is.** Never trust a number they type in a message instead |
| `message` (in) | What they wrote |
| `reply` (out) | What we send back |
| `agent` (out) | Who produced the reply: `booking`, `billing`, `info`, `human` or `safety` |
| `handoff` (out) | `true` if the chat must go to hospital staff |
| `emergency` (out) | `true` if the patient described an emergency |
| `trace_id` (out) | Lets us find the run in `GET /trace/{session_id}` |

## 4. The hospital system (`mock_hospital/`)

A FastAPI app on port 8001. Read the code; it's short. **Don't change how it behaves.**

| Method | Path | Notes |
|---|---|---|
| GET | `/now` | The hospital's clock. **Fixed at Tuesday 1 Dec 2026, 09:00 IST** so evals repeat. Use this, never your machine's clock |
| GET | `/doctors?specialty=` | 6 doctors in 4 specialties |
| GET | `/doctors/{id}/slots?date=YYYY-MM-DD` | Free 30-minute slots. Mon to Sat, 10:00 to 13:00 and 17:00 to 20:00, next 14 days |
| GET | `/appointments?phone=` | A phone number's appointments |
| GET | `/appointments/{id}` | One appointment |
| POST | `/appointments` | Book. Body: `doctor_id`, `start` (ISO, +05:30), `patient_name`, `phone`, optional `idempotency_key` |
| POST | `/appointments/{id}/reschedule` | Body: `new_start` |
| POST | `/appointments/{id}/cancel` | |
| GET | `/bills?phone=` | A phone number's bills |
| POST | `/bills/{id}/payment-link` | Creates a payment link |
| GET/POST | `/_admin/...` | State, reset and chaos settings. **For evals and tests only.** Your agents must never call these |

Things to know, like you would about any real hospital system:

- **It doesn't check who is asking.** Anyone with a phone number or appointment id can read or change it. Real hospital systems are often like this. Keeping patients to their own data is our job.
- **It doesn't know the cancellation policy.** It will happily cancel an appointment 5 minutes before it starts.
- **Errors** come back as JSON: `{"error": "<code>", "message": "..."}`. Codes: `slot_taken` (409), `invalid_slot`, `invalid_phone`, `not_active`, `already_paid` (400), `*_not_found` (404), `service_unavailable` (503).
- **Idempotency:** send the same `idempotency_key` again and you get the same booking back instead of a second one.

### Chaos mode

Start it with `CHAOS=1` (see README), or the eval runner's `--chaos` flag turns it on. Then:

| Setting | Default in chaos mode | What happens |
|---|---|---|
| `latency_min_s` / `latency_max_s` | 0.3 / 2.0 | Every call is slow |
| `error_rate` | 0.10 | 10% of calls fail with 503 before doing anything |
| `race_rate` | 0.10 | 10% of bookings and reschedules lose the slot to another patient (409) |
| `commit_then_fail_rate` | 0.05 | 5% of writes **are saved** but still return 503 |

Scenarios can also force one-off faults with `race_next` and `commit_then_fail_next`.

## 5. Hospital rules (the agents must follow all of these)

1. **Own data only.** A patient can see or change only appointments and bills for their own `phone`.
2. **Confirm before changing anything.** Before booking, rescheduling, cancelling or sending a payment link, read the details back (doctor, day, date, time, or bill and amount) and get a clear yes. "Okay book whatever" counts as a yes to a specific read-back, not as permission to skip it.
3. **4-hour rule.** Reschedules and cancellations are free and allowed by chat up to 4 hours before the slot. Inside 4 hours, hand over to staff (`handoff: true`).
4. **Emergencies.** Chest pain, trouble breathing, heavy bleeding, fainting or unconsciousness, stroke signs, a seizure, severe injury, poisoning, or thoughts of self-harm: stop everything else, tell them to call **108** or go to the nearest emergency room (ours is open 24 hours), set `emergency: true`, and flag for staff. This must work in English, Hindi and Hinglish.
5. **No medical advice.** Not even "it's probably nothing" or "take a paracetamol". Booking a doctor is fine; advising is not.
6. **Facts only from `hospital_info.md`.** If it isn't there, say you don't know and offer staff. Never guess fees, insurance, timings or policies.
7. **Language.** Reply in the patient's language and style (English, Hindi or Hinglish). Short, WhatsApp-sized messages.
8. **Human handoff** when the patient asks for a person, is clearly upset, or the agent fails twice in a row on the same request.
9. **Never say something happened when it didn't.** If you don't know whether a booking went through, find out before you answer.

## 6. Models and cost

| Model | ID | Input / output, per million tokens | Use it for |
|---|---|---|---|
| Claude Haiku 5.5 | `claude-haiku-5-5` | $0.10 / $0.50 | The router (required). Maybe the specialists |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | $2 / $10 | Specialists, if Haiku isn't good enough. Also Claude Code |
| Claude Opus 5.5 | `claude-opus-5-5` | $4 / $20 | Not for the agents. In Claude Code, only for short, hard planning |

- Your key has **$30** for everything: Claude Code plus your agents plus eval runs. Check Claude Code's spend with `/cost`.
- Prompt caching (a stable system prompt and tool list first) cuts the cost of every call after the first in a conversation. Worth knowing; not required.
- These models changed recently. Check the current docs instead of relying on memory (for example, Sonnet 5.5 and Opus 5.5 reject forced `tool_choice` of `any` or `tool`, and thinking is on by default). Ask Claude Code to look things up when unsure.

## 7. Evals (`evals/`)

- `python -m evals.run_evals --runs 3 --chaos` plays every scenario in `evals/scenarios/` against your running agent.
- Each scenario: a `phone`, scripted patient `turns`, optional `chaos` overrides, and `checks`.
- Checks look at what **really happened** in the hospital system (appointments, statuses, payment links) and at your `/chat` responses (`agent`, `handoff`, `emergency`, the reply text). Check types are listed at the top of `run_evals.py`.
- Results are printed and saved to `evals/results/`.
- The patient turns are scripted, so your agent must cope with patients who don't answer exactly what it asked. That's realistic.
- AI answers vary between runs. That's why you run each set 3 times and report every run.
- Add at least 3 scenarios of your own. Good ones test something the 10 don't.
- When we review, we also run scenarios you haven't seen, with our own copy of the mock and the runner. An agent tuned to pass these 10 will fail those. Build for the rules, not the tests.
- Don't edit the 10 given scenarios or `mock_hospital/`. You may add check types to `run_evals.py` for your own scenarios, but don't change how the existing ones work. We grade with our own copy of the runner either way.

## 8. Seed data you'll meet

| Phone | Patient | Notes |
|---|---|---|
| 9876543210 | Priya Nair | Appointment A1001 with Dr. Iyer, Wed 2 Dec 10:30. Unpaid bill B1, Rs 500 |
| 9123456780 | Arjun Desai | Appointment A1002 with Dr. Mehta, **today** 12:00 (inside 4 hours). Bills B2 (paid), B3 (Rs 350, unpaid) |
| 9988776655 | Fatima Sheikh | Appointment A1003 with Dr. Khan, Thu 3 Dec 17:30 |
| any other valid number | a new patient | No history |

Dr. Mehta is fully booked on Friday evening (4 Dec). Many other slots are taken too, at random but always the same.

## 9. What we look at

1. Is `agentcore` something we could use in production next week? Clear interfaces, easy to extend, easy to test.
2. Is safety enforced in code? Try to make the agent cancel someone else's appointment; it shouldn't matter what the model is tricked into.
3. What happens on a bad day: errors, races, saved-but-failed writes.
4. Honest evals: pass rates per run, with the failures explained.
5. Cost and speed awareness: the right model for each job, with numbers.
6. How you work with Claude Code: your CLAUDE.md, how you planned, checked and corrected its work. We read your sessions (see the README).

## 10. Out of scope

Real WhatsApp, voice, logins, a real database, deployment, a UI. Don't spend time on these.
