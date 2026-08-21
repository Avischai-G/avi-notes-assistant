# All Things Agentic Hackathon — official-rules findings

Verified directly on 2026-08-21 at 07:11 UTC. This is a practical reading of the published contest text, not legal advice.

## Decision in one minute

- Submit **Coroner in The Taskmaster** category.
- **Fortified Enterprise Fleet is not merely a theme.** Its outcome-level capabilities sit inside Section 6, which defines the Requirements, and Stage One is a pass/fail check that an entry includes the Submission Requirements and reasonably addresses a Challenge. However, the rules do **not** clearly say that every named Gemini Enterprise Agent Platform product must be used; those products are presented next to a “Recommended Tech” label, while a different list is expressly “Mandatory for all categories.”
- Keep the public limit of five AI analyses per caller per hour, but give the judges a private credential that bypasses that quota. Judge access must be free and unrestricted through **October 1, 2026 at 11:45 P.M. Pacific Time**.
- Do not spend the remaining build window adding Agent Registry, Memory Bank, Agent Gateway, Model Armor, or OpenTelemetry merely to rescue the Fortified category. Switching category needs no engineering; budget roughly **1–3 hours** to align the Devpost copy and demo narrative with Taskmaster.

Primary sources:

- [Official Rules](https://allthingsagentichackathon.devpost.com/rules)
- [Contest main page](https://allthingsagentichackathon.devpost.com/)
- [Devpost Terms of Service](https://info.devpost.com/legal/terms-of-service)

The Devpost terms settle source priority: “If there is any discrepancy or inconsistency between the terms and conditions of the Official Rules and disclosures or other statements contained in any Hackathon materials … the terms and conditions of the Official Rules shall prevail.” [source: Devpost](https://info.devpost.com/legal/terms-of-service "Terms of service - Devpost")

## Question 1 — Is Fortified Enterprise Fleet binding?

### Exact controlling text

Section 6 introduces the material as binding requirements:

> “Please find the Application Requirements and Submission Requirements outlined below (hereinafter, referred to collectively as the “Requirements”).”

> “Projects must be built within one of these three categories:”

The Fortified description then says:

> “Build a scalable network of institutional agents that hook into official enterprise infrastructure. Teams must demonstrate how agents are cataloged for cross-department use, how they safely maintain context across weeks of asynchronous operations, and how they interact with production data without violating enterprise compliance, data sovereignty, or security policies.”

It immediately enumerates Discovery & Lifecycle/Agent Registry, Core Execution & State/Agent Runtime and Memory Bank, Security & Governance/Agent Identity, Agent Gateway and Model Armor, and Telemetry/Agent Observability. [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#6-submission-requirements "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

Stage One makes the consequence explicit:

> “The first stage will determine via pass/fail whether the Submission meets a baseline level of viability, in that the Submission includes all Submission requirements, reasonably addresses a Challenge, and reasonably applies the requirements.” [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#8-judging "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

The implementation language is less categorical. The rules separately label Gemini 3.5+, one listed Google agent framework, and one Google Cloud infrastructure service as **“Mandatory for all categories,”** while the Fortified product list is followed by **“Recommended Tech to use (Gemini Enterprise Agent Platform).”** Entries must select “one category which represents your project,” and the Sponsor/Administrator may reassign one. [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#6-submission-requirements "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

### Reading

The theme-only reading is wrong. A Fortified entry has to reasonably address the Fortified challenge at Stage One. The three weighted criteria are not the whole gate: they apply in Stage Two only after the pass/fail baseline. Stage Two also contains track-specific questions under Innovation & Operational Utility, including whether Fortified genuinely warrants multiple agents and delegates intelligently. The Architectural Discipline subsection then uses apparently stale category names (“Continuous Action Engine,” “Evolving Knowledge Engine,” and “Multi-Agent Nexus”), so the precise category-specific architecture scoring is poorly drafted; the general 30% criterion still applies.

The opposite extreme is also unsupported. There is no mechanical rule saying “omit one named product and be disqualified,” and the only expressly mandatory technology list is the cross-category list. The safest construction is:

- The **outcomes** are binding: catalog/discovery, safe extended context, production-data interaction, compliance/data-sovereignty/security, and a scalable institutional network.
- The **named Google products** are recommended implementations, not individually mandated products. Equivalent implementations may plausibly satisfy the outcomes.
- Missing most or all of those outcomes can cause a Fortified entry to fail Stage One even though there is no per-product automatic-disqualification clause.

So the internal audit’s practical warning was directionally right, but “you must build every named product” was too strong.

### Honest category fit

| Category | Case for Coroner | Case against |
|---|---|---|
| **The Taskmaster** | Coroner autonomously performs a messy, multi-step operational workflow: pick up a silent run, coordinate six specialized ADK agents, diagnose it, and produce a restart plan in a Cloud Run/Firestore/Cloud Scheduler system. That is background heavy lifting for a real developer/operator friction. | The text says not to make an agent that only writes text. If the demo looks like “input logs, output report,” judges may decide it analyzes rather than acts. Show the scheduled trigger, delegation, evidence collection, Firestore state change, and durable restart artifact—not only prose appearing in a UI. |
| **Collaborative Partner** | The internal agents collaborate. | The published category is about collaboration with the user: clarifying questions, step-by-step guidance, captured feedback, and adaptation to the user. Coroner does not currently do those things. |
| **Fortified Enterprise Fleet** | Six specialized agents and a production-reliability use case fit the multi-agent flavor and its Stage Two delegation questions. | Coroner has no registry/discovery, authenticated agent identity/gateway, prompt-injection protection product, multi-week durable context, OpenTelemetry auditability, or demonstrated production-data governance. It therefore misses the category’s defining outcomes. |

### Recommendation and cost

Choose **The Taskmaster**. This is a category change, not an engineering project: **0 engineering hours**, plus approximately **1–3 content hours** to rewrite the submission and structure the demo around autonomous operational action. If the current demo does not visibly show the trigger, multi-agent delegation, and persisted side effects, allow another **2–4 hours** to capture a stronger run; no feature build is required.

The case against Taskmaster is real: Coroner’s final product is a written plan, and the category rejects agents that merely write text. The answer is not to pretend that weakness away. Demonstrate that generating the plan is the final artifact of an autonomous background incident workflow, with live, visible side effects and failure handling. If Coroner cannot show those actions, its fit is only moderate—but it is still materially better than the other two categories.

## Question 2 — Must judge testing be unrestricted?

### Exact controlling text

Section 6 says:

> “Access must be provided to an Entrant’s working Project (if available) for judging and testing by providing a link to a website, functioning demo, or a test build.”

> “If Entrant’s website is private, Entrant must include login credentials in its testing instructions.”

> “The Entrant must make the Project available free of charge and without any restriction, for testing, evaluation and use by the Sponsor, Administrator and Judges until the Judging Period ends.”

It also says judges may elect not to test and may judge from the description, images, and video. [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#6-submission-requirements "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

The schedule defines the endpoint:

> “Judging Period: September 1, 2026 (9:00 A.M. Pacific Time) – October 1, 2026(11:45 P.M. Pacific Time) (“Judging Period”).” [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#4-contest-period "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

The main page says the app need not be publicly accessible or live at the exact moment of submission or judging, to avoid unnecessary costs. [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/ "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost") That conflicts with the stricter Official Rules when an available working project is supplied. The incorporated Devpost terms say the Official Rules prevail over other Hackathon Website statements, so do not rely on the cost note as permission to throttle judges.

### Reading

The rule forbids **both** charging and restrictions on Sponsor/Administrator/Judge access. It is not merely a “no purchase necessary” rule. A five-analysis-per-hour ceiling is a restriction when applied to a judge, even though five calls may be practically enough.

The rule does **not** require unrestricted use for every public visitor. Its stated beneficiaries are the Sponsor, Administrator, and Judges. Public callers may remain rate-limited, and authentication is expressly contemplated because the immediately preceding sentence permits a private site with login credentials.

### Least-cost compliant arrangement

Keep the five-per-hour public quota and add one private **judge credential** that bypasses the quota:

1. Accept the credential through a login/password field or a secret header—not a URL query parameter that will leak into logs.
2. Store and compare it as a secret; do not hard-code it in the public repository.
3. Put the credential and exact use instructions in Devpost’s testing instructions, as the rule expressly permits.
4. Exempt authenticated judge traffic from the per-caller hourly quota through October 1, 2026 at 11:45 P.M. Pacific Time. Keep ordinary concurrency safety, logging, and budget alerts, but do not advertise a judge request ceiling.
5. Revoke the credential after the Judging Period.

Estimated engineering effort: **2–4 hours** if the limiter is centralized (bypass branch, secret/config, tests, deployment, instructions). If the browser UI needs a new credential flow, allow **4–6 hours**. The marginal Gemini/Vertex cost remains usage-dependent, but this avoids opening the expensive endpoint to the public.

Alternatives:

| Option | Compliance/risk | Engineering effort |
|---|---|---:|
| **Judge credential bypass (recommended)** | Directly fits the private-login sentence; leaves public protection intact. | 2–4 h; 4–6 h with new UI |
| Separate judge deployment | Can comply, but duplicates configuration and still incurs model-call cost. | 0.5–1 day plus operations |
| Much higher public ceiling plus hard billing cap | Still a restriction; a hard cap can make access disappear before judging ends. | 1–2 h, but not a clean compliance fix |
| Omit the hosted link | Main page permits non-public demos, but the Official Rules say access to an available working project must be provided and Coroner is already hosted. It also weakens Production Readiness evidence. | Minutes, but legally and competitively risky |
| Cached/fixed “judge demo” | Cheap calls, but may not behave as the described live AI project and can weaken the live-execution score. | 0.5 day or more |

## Other rule checks

### Private repository

The repository may be public or private. If private, the exact rule is:

> “If private, must give access to testing@devpost.com and cloudhackathons@google.com” [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#submission-requirements-entries-to-the-contest-must-meet-the-following-requirements "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

Also include step-by-step local/cloud spin-up instructions in the README. A private GitHub repository is expressly allowed even though one Stage Two judging prompt inconsistently says “public GitHub repository”; share the private repo with both addresses and make its documentation judge-readable.

### Demo video

Binding requirements (exact text):

- “Should include a short overview of the problem your Project is solving, the value proposition as well as a demo of the application in action . Must demonstrate the backend is running on Google Cloud (ie: Google Cloud Console, Cloud Run dashboard, Vertex AI logs, URL of .run, etc)”
- “It should not be longer than 4 minutes. If it is longer than 4 minutes, only the first 4 minutes may be evaluated.”
- “It must conform to the technical requirements set forth on the Contest site, including that the Submission must be uploaded to and made publicly visible on YouTube or Vimeo, and a link to the video must be provided on the Submission form on the Contest Site.”
- “It must be in English or include English subtitles.” [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#submission-requirements-entries-to-the-contest-must-meet-the-following-requirements "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

Stage Two further rewards a four-minute video that explains the friction and architecture and shows an **unedited, live execution** through terminal logs, database updates, or UI changes. That is a scoring instruction, not an additional video-host eligibility clause.

**Unlisted status is not conclusively settled by the demo clause.** It says “publicly visible,” but does not add “not unlisted.” Elsewhere, the optional bonus-content rule explicitly says “public (not unlisted),” showing the drafter knows the distinction. Devpost’s current help page likewise says to choose privacy settings that make the video publicly visible, without expressly deciding whether Unlisted counts. [source: Devpost Help Center](https://help.devpost.com/article/85-uploading-a-demo-video "Uploading a demo video - Devpost.com Help Center") The zero-risk choice is to set the demo to fully **Public**, verify it in a signed-out/incognito window, and not use Unlisted.

### Winner-notification windows

Section 8 says a potential winner who does not respond “within two days from the first notification attempt” is disqualified. It also says required verification documents must be returned “within two days following attempted notification.” [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#8-judging "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

Section 9 separately says:

> “The deadline for returning the Required Forms to the Administrator is ten (10) business days after the Required Forms are sent.” [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#9-prizes "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

The overlap is genuinely inconsistent: Section 8 includes a Declaration of Eligibility and Liability/Publicity Release in its two-day rule, while Section 9 defines the winner affidavit and other forms as “Required Forms” with ten business days. The rules do not state that one supersedes the other. Operationally, the **two-day window governs the safe response** because it is the shorter, specific verification deadline and expressly threatens disqualification. Monitor the Devpost email (including spam) and respond/return whatever is available within 48 hours; do not plan around ten business days.

### License and publicity

Ownership remains with the entrant, but entering grants Google a **perpetual, irrevocable, worldwide, royalty-free, non-exclusive** license to use, reproduce, adapt, modify, publish, distribute, publicly perform, create derivatives from, and publicly display the project for evaluation and promotion, including screenshots, animations, and clips. [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#12-intellectual-property-rights "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

The incorporated Devpost terms add a perpetual, worldwide, royalty-free, non-exclusive promotional/display license for Devpost, the Sponsor, and parties acting for the Sponsor. They do not transfer ownership unless contest-specific rules clearly require transfer and a prize is awarded; these Official Rules retain entrant ownership. [source: Devpost](https://info.devpost.com/legal/terms-of-service "Terms of service - Devpost")

Entering also grants publicity rights. Section 14 says participation consents to promotion/display of the submission and promotional use of the entrant’s name, likeness, photograph, voice, opinions, comments, hometown, and country, worldwide, without additional payment or review unless prohibited by law. [source: Google/Devpost](https://allthingsagentichackathon.devpost.com/rules#14-publicity "All Things Agentic Hackathon: Ready, Set, Agent! Build next-generation agents that run in the background, handle the heavy lifting of massive datasets, and automate complex workflows asynchronously. - Devpost")

## Things we must do

- **Submit as Taskmaster** and make it represent the project: “Select one category which represents your project.”
- **Keep the required stack visibly provable:** the rules label Gemini 3.5+, one listed Google agent framework, and one Google Cloud infrastructure service “Mandatory for all categories.”
- **Give judges unrestricted, no-charge access through October 1 at 11:45 P.M. PT:** use a judge credential that bypasses the public quota.
- **If the repo stays private, share it with both** `testing@devpost.com` **and** `cloudhackathons@google.com`; include reproducible spin-up instructions.
- **Submit the architecture diagram and public YouTube/Vimeo demo;** keep the decisive material inside four minutes, use English/subtitles, show the app acting live, and visibly prove the backend is on Google Cloud.
- **Monitor winner email and act within two days,** because Section 8 attaches disqualification to that period.
- **Enter only if the non-exclusive project license and publicity grant are acceptable.**

## Things we may safely skip

- **Skip the Fortified build-out**—registry/discovery, multi-week context, identity/gateway, Model Armor-equivalent controls, and OpenTelemetry—because Coroner should not enter that category. Those items are not mandatory across all tracks.
- **Skip a separate judge deployment** if a private judge credential cleanly bypasses the existing limiter.
- **Skip removing the public rate limit.** The unrestricted-access rule is expressly for the Sponsor, Administrator, and Judges, not every visitor.
- **Skip making the code repository public.** A private repository is expressly permitted when both named addresses receive access.
- **Skip optional content/social posts and extra Google models** unless pursuing bonus points; Section 6 labels them “Optional Developer Contributions.”
- **Skip anything after minute four of the demo.** The rules warn that only the first four minutes may be evaluated.

## Fetch record

All three pages returned HTTP 200 when fetched without an entrant login.

| Page | Fetched | SHA-256 of fetched HTML |
|---|---|---|
| Official Rules | 2026-08-21 07:07:56 UTC | `894da204e932cc50556204822e312f0a379b9e27cdcfcbe0ed74fdaacfec765b` |
| Contest main page | 2026-08-21 07:09:43 UTC | `b038c55831e20cdcf304f6bde40948307822d27d2794f6c9db252a9b078d4b5f` |
| Devpost Terms of Service | 2026-08-21 | `80a9fc937652b52c8949f591c94f30a8af6f610cc28652a1e60446c26605d5c9` |
