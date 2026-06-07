# Compliance & Legal Plan (GDPR) — Synkris Voice Agent

**Plain-language version for the team.** This is engineering/planning input, **not legal advice**.
Anything marked 🔴 must be reviewed by a real lawyer before we go live with real patients.

---

## 0. The one thing everyone must understand first

We are building a voice agent for a **UK dental practice**. That means:

1. **We handle health data.** "Booking a filling" or "an emergency appointment" tells you something
   about a person's health. Under UK GDPR this is **special-category data** — the *strictest* tier.
   Everything below is stricter than for a normal app because of this.

2. **We are the "processor", the practice is the "controller".**
   - **Controller** = the dental practice. They own the patient relationship and decide why data is used.
   - **Processor** = us (Synkris). We handle the data *on their instructions*.
   - This matters: some documents are *theirs* (Privacy Notice), some are *ours* (Security Policy),
     and some are a *contract between us* (the DPA).

3. **We are not compliant today — and that's OK for now.** We're on mock/fake data. The rule is
   simple: **no real patient data touches the system until the 🔴 items below are done.**

---

## 1. The legal documents & requirements (what each one is, in plain English)

| # | Requirement | What it actually is | Who owns it | Priority |
|---|---|---|---|---|
| 1 | **DPA** (Data Processing Agreement) | The contract between us and the practice saying what we can/can't do with their patients' data. | Us → signed by both | 🔴 Must-have |
| 2 | **DPIA** (Data Protection Impact Assessment) | A risk assessment document. **Legally required** because we use AI + health data. Walks through what could go wrong and how we prevent it. | Us (with practice) | 🔴 Must-have |
| 3 | **ROPA** (Record of Processing Activities) | A simple list: what data we hold, why, where, who we share it with, how long we keep it. | Us | 🔴 Must-have |
| 4 | **Privacy Notice** | The "how we use your data" text patients can read. The practice publishes it; we give them the AI/recording wording. | Practice (we supply content) | 🔴 Must-have |
| 5 | **Data Retention Policy** | How long we keep recordings, transcripts, logs — then auto-delete. | Us | 🔴 Must-have |
| 6 | **Deletion / Erasure Process** | How we delete *all* of one person's data on request ("right to be forgotten"). | Us | 🔴 Must-have |
| 7 | **SAR Process** (Subject Access Request) | How we help the practice when a patient asks "what data do you have on me?". | Us (assist practice) | 🟠 Before go-live |
| 8 | **Subprocessor List** | The list of other companies we use that touch the data (Retell, Twilio, etc.). Goes in the DPA; must stay current. | Us | 🔴 Must-have |
| 9 | **Breach Response Plan** | A simple runbook: if data leaks, who we call, what we do, the deadlines. | Us | 🟠 Before go-live |
| 10 | **Data Flow Diagram** | A picture of where data goes (phone → Retell → us → Dentally). Feeds the DPIA. | Us | 🟠 Before go-live |
| 11 | **Security Policy** | How we keep data safe (encryption, access control, etc.). | Us | 🟠 Before go-live |
| 12 | **Terms of Service** | Our commercial contract with the practice (pricing, liability, etc.). | Us | 🟠 Before go-live |
| 13 | **ICO Registration + fee** | We legally must register with the UK regulator (ICO) and pay a small annual fee (~£40–60). | Us | 🔴 Must-have (quick) |
| 14 | **Call recording + AI disclosure** | The agent must say at the start: "You're speaking to an AI assistant, this call is recorded." | Us (in the prompt) | 🔴 Must-have |
| 15 | **PECR compliance** (SMS & outbound calls) | Separate rules for text messages and any outbound/marketing calls. Matters for Phase 4 SMS + future recall calls. | Us | 🟠 At Phase 4 |
| 16 | **International Transfer check** (IDTA/SCCs) | If any vendor processes data in the USA, we need extra paperwork + a risk check. | Us | 🔴 Must-have (drives vendor choice) |
| 17 | **NHS DSP Toolkit + Caldicott** | Extra NHS-specific rules — **only if** the practice handles NHS patients (very common in UK dentistry). | Us + practice | 🔴 If NHS |
| 18 | **External legal review** | A real solicitor checks all of the above. Do **not** skip for health data. | External lawyer | 🔴 Must-have |
| 19 | **Cyber / professional indemnity insurance** | Insurance expected when handling health data. | Us | 🟠 Before go-live |

**Legend:** 🔴 = blocks going live with real patients · 🟠 = needed before go-live but not blocking the build.

---

## 2. Steps to get each one (the practical "how")

Grouped so the team can split the work.

### Group A — Quick admin (do this week, cheap, no blockers)
- **ICO registration** → fill the form on ico.org.uk, pay the fee. Half a day.
- **Insurance** → get quotes for cyber + professional indemnity.

### Group B — Documents we write ourselves (drafts first, lawyer reviews after)
- **ROPA** → fill a simple table (we already know most: name, DOB, phone, recordings, transcripts).
- **Retention Policy** → decide the numbers (e.g. delete recordings after 30 days, transcripts after 90).
- **Subprocessor List** → list every vendor + what data they see + their country.
- **Data Flow Diagram** → one diagram (phone → Retell → our backend → Dentally; + Twilio, Supabase).
- **Security Policy** → write down what we already do (HTTPS, encryption, access control) + gaps.
- **Breach Response Plan** → a one-page runbook with names, steps, the 72-hour rule.
- **Deletion & SAR processes** → write the steps; they depend on the architecture changes in §3.

### Group C — Documents that need the practice / a lawyer
- **DPIA** → start from an ICO template; we fill the technical parts, lawyer/practice review. 🔴
- **DPA** → use a standard processor DPA template, lawyer adapts it, both sign. 🔴
- **Privacy Notice wording** → we draft the AI/recording paragraph, practice adds it to their notice.
- **Terms of Service** → lawyer drafts from our commercial terms.
- **External legal review** → book a solicitor experienced in health-data / GDPR once drafts exist.

### Group D — Decisions that must happen before we build the real integration
- **Pick vendor regions (EU/UK).** See §4 — this is the most important and changes the tech stack.
- **Confirm NHS or private** patients → tells us if §1 item 17 (DSP Toolkit) applies.
- **Agree retention numbers** with the practice.

---

## 3. Changes to the architecture & plan

Good news: **none of these break what we've built.** They extend it. Most are cheap *now* and
expensive *later*, so we decide them before Phase 2 (real Dentally).

### Architecture changes
1. **Keep patient data in the PMS (Dentally), not in our database.**
   Our database stores only a *reference* (tenant id + the Dentally patient id) plus call info — never
   a second copy of the patient record. Less data we hold = less risk. *(Our PMS-interface design
   already supports this; we just must not duplicate the data.)*

2. **Build retention + auto-delete from day one.**
   Add a `retention` setting per practice (how many days to keep recordings / transcripts / logs) and a
   scheduled job that deletes old data automatically. This single feature satisfies the Retention Policy
   *and* the Deletion requirement.

3. **Tag every stored record with `tenant_id` + patient reference.**
   So when someone says "delete all my data" or "what do you hold on me", we can find it everywhere in
   one query. Very hard to add later — do it now.

4. **Never log personal data.** Name, DOB, phone, and transcripts must not appear in our application
   logs. Write this rule down and follow it.

5. **Encryption at rest** on the database (Supabase supports this) + **HTTPS everywhere** (already have it).

6. **Audit log on the dashboard** (Phase 5): record who viewed which call/transcript. Required for health data.

7. **Consent line in the agent's opening** (Phase 1 prompt): "You're speaking to an AI assistant and
   this call is recorded." Person B owns the prompt; we specify the requirement in the contract.

### Plan changes
- **Add a "Phase 0.5 — Compliance gate" to `PROJECT_PLAN.md`** that must be passed before Phase 2
  touches real Dentally data. (See §5 for which items land in which phase.)
- **Phase 4 (SMS):** add PECR check + "service message vs marketing" rule.
- **Phase 5 (dashboard):** add cookie consent + audit logging + access control.

---

## 4. Tech stack / service choices — decide NOW (driven by the legal rules)

The **#1 rule: keep all patient data inside the UK/EU.** If a vendor processes it in the USA, we need
extra legal paperwork (IDTA) *and* the practice has to accept the risk — often a dealbreaker for health
data. So we choose vendors on **data location first**, features second.

| Layer | Service | What to check before choosing | Recommendation |
|---|---|---|---|
| **Database / backend** | **Supabase** | Choose an **EU/UK region** at project creation; turn on encryption at rest. | ✅ OK — pick EU region |
| **Voice AI** | **Retell** | **Where does it process the call + which LLM does it use, and in what country?** Does it train on our audio? Will it sign a DPA? | ⚠️ **Must confirm** — this is the biggest risk. If US-only with no DPA, reconsider. |
| **Telephony / SMS** | **Twilio** | Choose **EU/UK numbers + region**; Twilio signs a DPA and offers EU data residency. PECR for SMS. | ✅ OK — pick EU region |
| **Payments** | **Stripe** | PCI-compliant; if we only use payment *links* we barely touch card data. Confirm EU entity. | ✅ OK |
| **Hosting** | **Railway / Render** | Pick an **EU region**. Confirm they'll sign a DPA. | ✅ OK — pick EU region |
| **PMS** | **Dentally / Cliniko** | UK-based, already health-data compliant. They are the system of record. | ✅ OK |
| **LLM (behind Retell or ours)** | TBD | If we ever call an LLM directly: use one that **won't train on our data** and offers EU processing. | ⚠️ Confirm region + no-training |

**Action:** before Phase 2, get written confirmation from **Retell** (and any LLM) on: (a) data location,
(b) whether they train on our data, (c) that they'll sign a DPA. This one answer can change our stack.

---

## 5. Which phase does each thing go in?

Mapped onto the existing 6-phase plan.

### Phase 0 — Foundation (now, before any real data)
- ICO registration + insurance quotes (Group A)
- Pick EU/UK regions for every vendor (§4) — **especially confirm Retell**
- Confirm NHS vs private (decides if DSP Toolkit applies)
- Start the DPIA, draft ROPA, retention policy, subprocessor list, data-flow diagram
- Build retention + tenant-tagging into the architecture (§3.1–3.4)

### Phase 1 — Call works end to end (dummy data)
- Add the **AI + recording disclosure** to the agent's opening line
- Still mock data — safe to keep building

### 🔴 Phase 0.5 — Compliance gate (NEW — must pass before Phase 2)
**Do not connect real Dentally / take a real patient call until ALL of these are done:**
- DPA signed with the practice
- DPIA completed
- External legal review done
- Deletion + SAR process working end to end
- Vendor regions confirmed EU/UK + DPAs signed (Retell, Twilio, Supabase, hosting)
- Privacy Notice wording given to the practice and published

### Phase 2 — Real Dentally integration
- Keep patient data in Dentally, only references in our DB (§3.1)
- Encryption at rest confirmed

### Phase 3 — Core conversation flows
- Make sure escalation/transfer doesn't leak data; breach plan finalised

### Phase 4 — Notifications (SMS)
- PECR compliance; service-message vs marketing rule

### Phase 5 — Dashboard
- Cookie consent, audit logging, access control on transcripts

### Ongoing
- Keep subprocessor list current; review DPIA when anything changes; breach drills

---

## 6. The 60-second summary for the team

- We handle **health data**, so the rules are strict. We're **not compliant yet** — that's fine while
  on fake data.
- **Hard rule:** no real patient data until the **🔴 Compliance Gate (Phase 0.5)** is passed.
- **Biggest decision right now:** confirm **Retell (and every vendor) keeps data in the EU/UK** and
  will sign a DPA. This can change our tech stack, so do it first.
- **Cheapest wins right now:** register with the ICO, and build **auto-deletion + tenant-tagging** into
  the architecture before we write the real integration.
- **Don't skip the lawyer.** Our docs are drafts; a solicitor signs them off.

---

## 7. Checklist (tick as we go)

> **PMS note (2026-06-07):** Dentally is **not decided** — open API issue. We proceed on **MockPMS** and
> pick **Cliniko or Dentally** later. The compliance work below is the same whichever we choose.

### Phase 0 — Foundation (now, on mock data)
- [ ] Register with the ICO + pay the fee
- [ ] Get cyber + professional indemnity insurance quotes
- [ ] Confirm Retell data region (EU/UK?) + does it train on our data? + will it sign a DPA?  ← **biggest risk, do first**
- [ ] Pick EU/UK region for Supabase, Twilio, hosting (Railway/Render)
- [ ] Confirm NHS vs private patients (decides if DSP Toolkit applies)
- [ ] Draft ROPA (record of what data we hold)
- [ ] Draft Retention Policy (agree the keep-for-X-days numbers with the practice)
- [ ] Draft Subprocessor List
- [ ] Draft Data Flow Diagram
- [ ] Draft Security Policy
- [ ] Draft Breach Response Plan
- [ ] Start the DPIA
- [ ] **Architecture:** build retention + auto-delete
- [ ] **Architecture:** tag every record with tenant_id + patient reference
- [ ] **Architecture:** no personal data in logs
- [ ] **Architecture:** keep patient data in the PMS, only references in our DB

### Phase 1 — Call works end to end (dummy data)
- [ ] Add the AI + recording disclosure to the agent's opening line

### 🔴 Phase 0.5 — Compliance Gate (must pass before Phase 2 / any real patient)
- [ ] DPA signed with the practice
- [ ] DPIA completed
- [ ] External legal review done
- [ ] Deletion process working end to end
- [ ] SAR process working end to end
- [ ] Vendor regions confirmed EU/UK + DPAs signed (Retell, Twilio, Supabase, hosting)
- [ ] Privacy Notice wording given to the practice + published
- [ ] Terms of Service in place

### Phase 2 — Real PMS integration
- [ ] PMS chosen (Cliniko or Dentally)
- [ ] Patient data stays in the PMS; our DB holds only references
- [ ] Encryption at rest confirmed on the database

### Phase 4 — Notifications (SMS)
- [ ] PECR compliance check
- [ ] Service-message vs marketing rule applied

### Phase 5 — Dashboard
- [ ] Cookie consent banner
- [ ] Audit logging (who viewed which call/transcript)
- [ ] Access control on transcripts

### Ongoing
- [ ] Keep subprocessor list current
- [ ] Review DPIA whenever something changes
- [ ] Breach-response drill

---

*This file is a living plan. Update it as decisions are made. Last updated: 2026-06-07.*
