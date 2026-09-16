# BrandMatch — Roadmap and Definition of Done

**Client: ICA — Instituto Colombiano Agropecuario.**

## The problem

In many cattle-raising regions, electronic identification — GPS collars, RFID ear
tags — costs more than ranchers can justify. Hot-iron brands (*hierros*) are already
on the animals, cheap, permanent, and recognised as a mark of ownership.

**BrandMatch centralises brand registrations in one database that ICA loads itself,
and lets anyone authorised identify a brand from a phone photo.**

### What this is, and what it is not

It answers **"who owns this animal?"** — at a checkpoint, a livestock market, a
slaughterhouse, a roadside stop, or when a stray turns up.

It does **not** answer "where is this animal right now?" the way GPS does. One later
feature recovers part of that: if authorised users opt in, each search can record
where and when a brand was seen, building a last-seen trail.

**A match is a lead, not proof.** Brands look alike and hides distort them. The system
returns a ranked shortlist; a person confirms.

---

## Decisions made

| Question | Answer |
| --- | --- |
| Country | Colombia |
| Client | ICA |
| Who loads the data | **ICA, themselves** — one brand at a time and in bulk |
| Real data | Requested **after** presenting a demo |
| Accuracy needed | Correct brand in the **top 5**; top 10 is a nice-to-have |
| Budget | **Demo only for now** — no paid hosting |

---

## How "done" works

Nothing gets built twice and nothing stays half-finished. Three levels.

### 1. A task is done when…

Every task is an `F` entry in `feature_list.json` and, before work starts, has a
**milestone**, **verification** steps, and an **out_of_scope** list.

It is `passing` only when every verification step was run and its real output is
recorded in `evidence`, `bash scripts/verify.sh` passes, and — if users can see it —
it has been confirmed on the deployed site.

**Once `passing`, a task is closed for good.** A later breakage is a new task that
references it. Scope discovered mid-task becomes a new task.

### 2. A milestone is done when…

Every exit criterion is checked with evidence. Then it is **frozen**: no new work except
fixing breakage. Nothing outside the current milestone starts without your approval.

### 3. The service is done when…

**M5 is met: a 30-day pilot with ICA** using real brands and real searches. Until then
it is a prototype, however polished.

---

## Milestones

| | Milestone | Question it answers | Status |
| --- | --- | --- | --- |
| **M0** | Demo, hardened | Does the idea run end to end? | **1 deploy check left** |
| **M1** | **ICA demo** | Will ICA share data and want this? | Specified, 9 tasks |
| **M2** | Prove it on ICA's real data | Does a real phone photo find the right brand? | After ICA shares data |
| **M3** | The real registry | Can ICA staff load their whole registry, permanently? | Not started |
| **M4** | Field search | Does it work next to a cow on weak signal? | Not started |
| **M5** | Operate it — pilot with ICA | Can people rely on it? | Not started |

---

### M0 — Demo, hardened *(current)*

**Exit criteria**
- [x] Deployed demo returns ranked matches for an uploaded image.
- [x] Errors, CORS, cold-start messaging and themes correct and deployed.
- [x] Backend and frontend automated tests, each proven able to fail.
- [ ] **F19** — dependencies pinned, confirmed by one production deploy.
- [x] **F20** — filenames and API messages render as text, never as HTML.

---

### M1 — ICA demo

**Goal:** in a five-minute presentation, ICA sees their own staff register brands —
one by one and in bulk — and identify one from a photo, with the registration details
on screen. Built to earn the real data that M2 needs. **No hosting cost.**

**The demo, as it will be presented**
1. Open the site: a registry of fictional Colombian brands, in Spanish.
2. Register one brand with its details. Search for it — it comes back first.
3. Import 20 brands at once from a spreadsheet and a folder of images; see which rows
   succeeded and why any failed.
4. Try to register a brand that looks like an existing one — the system warns.
5. Take a photo with a phone of a printed brand — the right one appears in the top 5
   with its owner, farm and municipality.
6. Show the simulated field-photo accuracy figure, and why real data is the next step.

**Exit criteria**
- [ ] F21–F29 all `passing`.
- [ ] The six steps above run end to end on the **deployed** site, rehearsed once from
      a cold server.
- [ ] Every screen that shows registry data says it is **fictional demo data**.
- [ ] The known limitation is written into the demo script and stated honestly:
      brands registered during the demo reset when the free server restarts. The
      fictional registry itself is always there.

**Tasks** — full specs, checks and out-of-scope in `feature_list.json`:

| | Task |
| --- | --- |
| F21 | The whole interface in Spanish |
| F22 | A fictional Colombian brand registry with details replaces the scraped images |
| F23 | Results show the registration details |
| F24 | Register a single brand from the page |
| F25 | Bulk import from a spreadsheet and images |
| F26 | Warn when a new brand resembles an existing one |
| F27 | Phone camera capture, and photos shrunk before upload |
| F28 | Simulated field-photo benchmark — an honest number for the pitch |
| F29 | Demo-day reliability: warm-up, reset, rehearsal script |

**Questions to ask ICA in the meeting** — their answers scope M2 and M3:
1. How are brands registered today, and who holds the records — paper books, scans,
   a database?
2. Which fields does a registration contain?
3. Could you share a sample — around 100 registered brands, and photos of some of
   those brands on live animals?
4. Who would load brands, and who would search — which roles?
5. Where would it be used first — movement checks, markets, slaughterhouses, theft
   reports?

---

### M2 — Prove it on ICA's real data *(the go/no-go gate)*

**Starts when ICA provides data.** The demo compares images it generated itself; only
real photos of brands on live animals — hair, scarring, curvature, angle, light — show
whether this works.

**Exit criteria**
- [ ] A labelled, frozen evaluation set: **≥ 100 registered brands** and **≥ 300 photos**
      of them on real animals, including brands that are **not** registered.
- [ ] One command reports top-1, top-5 and top-10 accuracy.
- [ ] At least three approaches measured (current MobileNetV2, CLIP, DINOv2), with and
      without preprocessing.
- [ ] The chosen approach puts the correct brand in the **top 5** for the agreed share of
      photos not used for tuning. **Proposed: ≥ 90%.** Top 10 reported alongside.
- [ ] A similarity threshold under which an **unregistered** brand is reported as "no
      confident match" rather than pinned on a stranger, with the false-match rate
      written down. Wrongly naming an owner is the worst error this system can make.
- [ ] A written go / no-go decision.

---

### M3 — The real registry

**Exit criteria**
- [ ] Data model agreed with ICA (from the meeting's answers).
- [ ] ICA staff sign in; each change is attributed to a person.
- [ ] Brands, images and vectors live in **permanent storage** and survive redeploys —
      proven by redeploying and searching again.
- [ ] Bulk import of ICA's real format at their scale, with a per-row report and no
      duplicates on re-import.
- [ ] Similar-brand review workflow, not just a warning.
- [ ] Every criterion has an automated test.

### M4 — Field search

**Exit criteria**
- [ ] Always-on hosting: a search never waits for a server to wake.
- [ ] p95 search time **≤ 5 s** at the agreed pilot scale.
- [ ] Filters: department, municipality, position on the animal.
- [ ] Owner contact visible **only to authorised roles**, proven by a test.
- [ ] Every search logged; optional opt-in location for a last-seen trail.

### M5 — Operate it: pilot with ICA

**Exit criteria**
- [ ] Roles enforced and tested.
- [ ] Daily backups and **a restore actually performed**.
- [ ] Monitoring and alerts that reach a person.
- [ ] Owner data handled under **Ley 1581 de 2012** (Colombian personal-data law), with
      terms of use and owners able to request their data.
- [ ] Security review: authentication, uploads, rate limiting, injection.
- [ ] Monthly cost agreed.
- [ ] **30-day pilot with ICA**, meeting M2's accuracy target in real use.

---

## Biggest risks, in order

1. **Recognition on real photos.** Untested until M2. The demo cannot prove it.
2. **Getting the data.** If ICA's registry is paper or scans, digitising it may be the
   largest single piece of work.
3. **Look-alike brands.** Simple letters and numbers repeat across owners. Always a
   shortlist with department and position, never a verdict.
4. **Misuse.** A searchable directory of owners is useful to thieves too. Access control
   is part of the product.
5. **Connectivity.** Rural signal and low-end phones shape the field experience.

---

## What carries over from today

**Keeps:** the FastAPI service, the normalise → embed → search pipeline, the test
approach, and this working method.

**Replaced in M1:** the 78 scraped web images — not Colombian, not ours to use, and
their filenames look like what they are.

**Replaced in M3–M4:** storing the index inside the build, and Render's free tier with
its ~100-second cold starts.

**Possibly replaced in M2:** MobileNetV2, if another model does better on real photos.
