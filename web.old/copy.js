/* The hackathon copy, kept out of app.js because it is prose, not logic.
   Every `quote` block is verbatim from the official rules or overview page
   (read live 2026-08-21); everything else is our own writing. The renderer in
   app.js keeps that distinction visible on the page. */

const RULES_URL = 'https://allthingsagentichackathon.devpost.com/rules';

/* Shared by all three category pages: the stack every category must use. */
const MANDATORY = {
  h: 'The stack every category must use',
  body: [
    { quote: 'Mandatory for all categories: 1) Gemini 3.5 or newer accessed through Gemini API or '
      + 'Vertex AI, 2) AND at least one Google Agent Framework: Google ADK, GenAI SDK, Antigravity '
      + 'SDK or GenKit 3) AND at least one Google Cloud infrastructure service (such as Cloud Run, '
      + 'Cloud SQL, Firestore, GKE, Pub/Sub).', from: 'Official rules' },
    { table: [
      ['Gemini 3.5 or newer, via Gemini API or Vertex AI', '`gemini-3.5-flash` on Vertex AI.'],
      ['At least one Google Agent Framework', 'Google ADK (`google-adk`), using `SequentialAgent` and `ParallelAgent`.'],
      ['At least one Google Cloud infrastructure service', 'Cloud Run hosts the service; Firestore stores the cases; Cloud Scheduler drives the sweep.'],
    ] },
    { p: 'All three are satisfied — and all three are satisfied by every serious entry, so this '
       + 'table earns no points on its own. It is a gate, not a score.' },
  ],
};

const CATEGORIES = {
  taskmaster: {
    name: 'Taskmaster',
    entered: true,
    stance: 'Coroner is entered in this category.',
    quotes: [
      { from: 'Official rules — the category', text: 'Taskmaster: Build a Complete Workflow, Not '
        + 'Just a Chatbot. Don’t just make an agent that writes text. Make one that takes '
        + 'action. Find a messy, multi-step chore in your job, classes, or personal life. Build an '
        + 'agent that handles the details, sends the right info to the right places, and proves it '
        + 'can do the heavy lifting for you.' },
      { from: 'Official rules — what the judges are told to ask', text: 'For TaskMaster: Does the '
        + 'agent successfully intercept and complete a multi-step background workflow without human '
        + 'intervention? Did the team successfully utilize the "Bring Your Own Friction" (BYOF) '
        + 'mandate to solve a unique, personal problem?' },
    ],
    lead: 'Read together, the category text and the judging question ask for six things. Five are '
        + 'quoted or directly restated from the rules; the sixth is the mandatory stack.',
    checks: [
      { v: 'yes', need: 'A complete workflow, not a chatbot.',
        note: 'Coroner has no chat interface at all. There is no prompt box, and nothing in the '
            + 'product accepts a user question. The unit of work is a case file, produced end to '
            + 'end without a conversation.' },
      { v: 'yes', need: 'An agent that "takes action" rather than writes text.',
        note: 'The pipeline does not stop at a diagnosis. `revive` writes a restart plan, and the '
            + 'service POSTs that plan to a second Cloud Run service, which queues it. The output '
            + 'of an autopsy is a queued restart, not a paragraph.' },
      { v: 'yes', need: 'A "messy, multi-step chore" from the entrant’s own job, classes or personal life.',
        note: 'The chore is triaging dead agent runs in the entrant’s own orchestrator. The '
            + 'corpus is 39 real dead runs from that system. This is the BYOF mandate read '
            + 'literally: the friction is the author’s, and the evidence of it is the '
            + 'author’s own wreckage.' },
      { v: 'yes', need: 'It "handles the details, sends the right info to the right places."',
        note: 'Each case is written to Firestore and served at `/api/case/{run_id}`; the restart '
            + 'plan goes to the queueing service; the fleet report aggregates all 39 into ranked '
            + 'prescriptions at `/api/fleet`.' },
      { v: 'yes', need: 'It "intercept[s] and complete[s] a multi-step background workflow without human intervention."',
        note: 'The strongest claim here, and it is literal. Cloud Scheduler pings the service every '
            + '15 minutes. The sweep looks for runs that have stopped moving and are not in a '
            + 'terminal state, presumes them dead, and autopsies them unprompted. Nobody requests '
            + 'an autopsy. `POST /api/autopsy` exists, but the shipped corpus was not produced by '
            + 'anyone pressing it.' },
      { v: 'yes', need: 'Gemini 3.5 or newer, a Google Agent Framework, and a Google Cloud service.',
        note: 'See the stack table below.' },
    ],
    sections: [
      { h: 'What the corpus shows',
        body: [
          { fleetFigures: true },
          { p: 'Those four numbers are not typed into this page. They are read from `GET /api/fleet` '
             + 'when you load it, so they cannot drift away from the corpus they describe.' },
          { p: 'That 92% is the argument for the whole category fit: a run that reports an error '
             + 'can be handled by an alert. These did not report anything, so no alert could fire, '
             + 'and a human only finds them by noticing that nothing has happened. That noticing is '
             + 'the chore Coroner takes over.' },
        ] },
      { h: 'Where Coroner is weaker',
        weak: true,
        body: [
          { p: 'Two things worth stating plainly rather than leaving for a judge to find.' },
          { ul: [
            'The 74 abandoned steps and 36 revivable runs are a measurement of the wreckage, not '
            + 'proof that Coroner recovered it. Coroner queues restart plans; the shipped evidence '
            + 'does not include a count of runs that were successfully restarted and then finished.',
            'The `wasted_effort` and `revivable` fields are the model’s judgement recorded in '
            + 'the case file, not independently verified outcomes. They are presented as the '
            + 'certificate’s finding, which is what they are.',
          ] },
        ] },
      { h: 'Architectural discipline — 30% of the score',
        body: [
          { p: 'The rules break this criterion into three named sub-criteria — "The Continuous '
             + 'Action Engine", "The Evolving Knowledge Engine" and "The Multi-Agent Nexus" — and '
             + 'never say which category each belongs to. Those three names appear nowhere else on '
             + 'the rules page. So this section answers the substance of all three and claims none '
             + 'of the labels.' },
          { quote: 'For The Continuous Action Engine: Judges will look for a robust architecture. '
            + 'Did you implement a clean, modularized, ease of maintenance system? How does the '
            + 'system handle state management? Are the tools properly isolated and scoped for '
            + 'security?', from: 'Official rules' },
          { p: 'Endpoints are thin; everything interesting is in `app/`. State lives in Firestore '
             + 'behind three calls in `app/store.py`, so nothing upstream knows whether it is '
             + 'talking to a database or a directory of JSON on a laptop. The two endpoints that '
             + 'spend money are rate limited; the trace parser bounds step count, text length, JSON '
             + 'depth and node count on hostile input; and every trace is pattern-redacted before a '
             + 'single byte reaches Vertex AI.' },
          { quote: 'For The Evolving Knowledge Engine: Judges will evaluate your data architecture. '
            + 'This includes intelligent schema design, efficient vector embedding strategies. How '
            + 'efficiently does the system manage massive context windows?', from: 'Official rules' },
          { p: 'Every stage has its own Pydantic schema and returns structured output, not prose, '
             + 'so the next stage reads fields rather than parsing English. Coroner uses no vector '
             + 'store: each autopsy reads one run’s trace, and the rule-based evidence pass in '
             + '`app/findings.py` is what keeps the model’s context to the signals that '
             + 'matter instead of the whole trace. That is a deliberate absence, not an oversight.' },
          { quote: 'For The Multi-Agent Nexus: Judges are looking for good use of agent workflows. '
            + 'Is there a clear, strictly enforced separation of concerns between agents? Is the '
            + 'inter-agent routing logic failure-tolerant (e.g., how does the system recover if a '
            + 'worker agent loops or returns a hallucination)?', from: 'Official rules' },
          { p: 'Separation is enforced by schema: triage may only emit hypotheses, an investigator '
             + 'may only emit verdicts on those hypotheses, `certify` may only choose among what '
             + 'survived. The tolerance for a hallucinating worker is the middle stage itself — '
             + 'three investigators with different lenses, each instructed to destroy the '
             + 'hypotheses rather than confirm them, and each told to treat a trace too thin to '
             + 'decide as a failure to survive. In 8 of 39 cases that stage overturned the run’s '
             + 'own recorded cause of death.' },
        ] },
      MANDATORY,
      { h: 'The prize',
        body: [
          { quote: 'The Taskmaster\n•$20,000 in USD\n• $2,000 in Google Cloud Credits for '
            + 'use with a Cloud Billing Account\n• Virtual Coffee with a Google Team '
            + 'Member\n• Social Promo', from: 'Official rules' },
          { p: 'Coroner is also automatically in the running for the Grand Prize, which goes to the '
             + '"highest-scoring Submission across all categories". Note that "Each Project is '
             + 'eligible for up to one (1) Prize."' },
        ] },
    ],
  },

  partner: {
    name: 'Collaborative Partner',
    entered: false,
    stance: 'Coroner is not entered in this category and does not fit it. This page says so.',
    quotes: [
      { from: 'Official rules — the category', text: 'Collaborative Partner: Build an agent that '
        + 'leads the way and takes notes. It should ask clarifying questions, guide the user '
        + 'step-by-step, and have a clear way to capture feedback, so it constantly adapts to the '
        + 'user’s unique way of thinking.' },
      { from: 'Official rules — what the judges are told to ask', text: 'For Collaborative Partner: '
        + 'Does the agent actively synthesize or mutate data, rather than just reading it? Did the '
        + 'team ingest unusual, messy, or highly complex unstructured data streams?' },
    ],
    lead: 'Eight requirements, read off the category text and the judging question. Coroner meets '
        + 'one squarely, half-meets two, and fails the four that define the category.',
    checks: [
      { v: 'partial', need: 'The agent "leads the way and takes notes."',
        note: 'The wrong half. Coroner takes notes exhaustively. It leads no one, because there is '
            + 'no one there.' },
      { v: 'no', need: 'It "ask[s] clarifying questions."',
        note: 'Deliberately not — this is the sharpest mismatch. Coroner’s `revive` agent is '
            + 'instructed that if a run died waiting on a human, the restart plan must not say the '
            + 'human should answer, because that is precisely what already failed. It writes an '
            + 'assumption the orchestrator can proceed under instead, chosen so that being wrong is '
            + 'cheap and visible. The category asks for an agent that asks; Coroner is built to '
            + 'stop asking. Eight of the 39 runs in the corpus died of `STALLED_ON_USER` — the '
            + 'category’s central mechanism is, in this corpus, a documented cause of death.' },
      { v: 'no', need: 'It "guide[s] the user step-by-step."',
        note: 'There is no interactive flow. The user reads a finished case file.' },
      { v: 'no', need: 'It has "a clear way to capture feedback."',
        note: 'There is no feedback mechanism. Nothing in the product accepts user input that '
            + 'changes a future autopsy.' },
      { v: 'no', need: 'It "constantly adapts to the user’s unique way of thinking."',
        note: 'There is no per-user state and no personalisation.' },
      { v: 'yes', need: 'It "actively synthesize[s] or mutate[s] data, rather than just reading it."',
        note: 'This one Coroner meets squarely. The pipeline turns a raw trace into hypotheses, '
            + 'three adversarial verdicts, a certificate and a restart plan, and the fleet stage '
            + 'synthesises 39 cases into 6 ranked prescriptions.' },
      { v: 'partial', need: 'The team "ingest[s] unusual, messy, or highly complex unstructured data streams."',
        note: 'Agent run traces are an unusual input, and they are messy in the way that matters: '
            + '92% of them contain no error to read, and the corpus includes runs whose own ledger '
            + 'disagrees with their own board. But they arrive as structured JSON, not as an '
            + 'unstructured stream.' },
      { v: 'yes', need: 'The mandatory stack.',
        note: 'Met — but that is common to all categories and earns nothing here.' },
    ],
    sections: [
      { h: 'Verdict',
        weak: true,
        body: [
          { p: 'Coroner satisfies one requirement and part of two more, and fails the four that '
             + 'define the category. A Collaborative Partner is defined by the loop between agent '
             + 'and human. Coroner’s premise is that this loop is where runs go to die. '
             + 'Entering it here would be arguing against the project’s own evidence.' },
        ] },
      MANDATORY,
    ],
  },

  enterprise: {
    name: 'Fortified Enterprise Fleet',
    entered: false,
    stance: 'Coroner is not entered in this category and does not fit it. This page says so.',
    quotes: [
      { from: 'Official rules — the category', text: 'Fortified Enterprise Fleet: Build a scalable '
        + 'network of institutional agents that hook into official enterprise infrastructure. Teams '
        + 'must demonstrate how agents are cataloged for cross-department use, how they safely '
        + 'maintain context across weeks of asynchronous operations, and how they interact with '
        + 'production data without violating enterprise compliance, data sovereignty, or security '
        + 'policies.' },
      { from: 'Official rules — what the judges are told to ask', text: 'For Fortified Enterprise '
        + 'Fleet: Is the task complex enough to warrant a multi-agents system? Does the system '
        + 'intelligently delegate tasks to specialized sub-agents? Did they build this for an '
        + '"Unlikely Hero" outside of standard corporate roles?' },
    ],
    lead: 'Coroner scores on the two multi-agent judging questions and fails the category '
        + 'definition itself.',
    checks: [
      { v: 'no', need: '"A scalable network of institutional agents."',
        note: 'Coroner is one service running one six-agent pipeline. It is not a network of agents '
            + 'belonging to an institution.' },
      { v: 'no', need: 'It "hook[s] into official enterprise infrastructure."',
        note: 'It reads its own orchestrator’s traces. It touches no enterprise system of record.' },
      { v: 'no', need: 'Agents are "cataloged for cross-department use."',
        note: 'There is no registry, no versioning surface, and no second department. Nothing '
            + 'publishes Coroner’s agents for anyone else to discover.' },
      { v: 'partial', need: 'They "safely maintain context across weeks of asynchronous operations."',
        note: 'Narrower than it sounds. Coroner is genuinely asynchronous and genuinely '
            + 'long-running: Cloud Scheduler drives it every 15 minutes with no session behind it, '
            + 'and cases persist in Firestore indefinitely. But the context it maintains is the '
            + 'case corpus, not per-user memory across weeks of an ongoing engagement, which is '
            + 'what Memory Bank in the platform list describes.' },
      { v: 'no', need: 'They "interact with production data without violating enterprise compliance, '
            + 'data sovereignty, or security policies."',
        note: 'Not demonstrated. Coroner reads run traces from its own project and writes to its own '
            + 'Firestore database. There is no compliance boundary being respected here, because '
            + 'there is no compliance boundary in the deployment. Claiming otherwise would be '
            + 'inventing a control that does not exist.' },
      { v: 'yes', need: '"Is the task complex enough to warrant a multi-agents system?"',
        note: 'The one judging question Coroner answers well. The three investigators exist because '
            + 'a single pass produces plausible causes rather than tested ones; each is instructed '
            + 'to DESTROY the triage hypotheses through its own lens — timeline, counterfactual, '
            + 'competing-explanation — and to treat a trace too thin to decide as a failure to '
            + 'survive. Of the 39 cases, 8 had the run’s own recorded cause overturned by that '
            + 'process.' },
      { v: 'yes', need: '"Does the system intelligently delegate tasks to specialized sub-agents?"',
        note: '`triage` → three parallel investigators → `certify` → `revive`, as an ADK '
            + '`SequentialAgent` wrapping a `ParallelAgent`, with separate schemas per stage.' },
      { v: 'partial', need: 'Built for an "Unlikely Hero" outside of standard corporate roles.',
        note: 'Arguable, and we do not lean on it. Coroner is built for a solo operator running '
            + 'their own agent fleet, which is outside standard corporate roles. But the rules do '
            + 'not define the term, so this is our reading rather than a requirement we can show we '
            + 'met.' },
    ],
    sections: [
      { h: 'The platform list, and why its status is unclear',
        body: [
          { p: 'The rules place four further bullets immediately after this category. In the page '
             + 'markup they are nested inside the Fortified Enterprise Fleet list item, but the line '
             + '"Recommended Tech to use (Gemini Enterprise Agent Platform):" appears *after* them, '
             + 'as an empty list item. So they read either as requirements of this category or as '
             + 'the contents of a recommendation list whose heading got misplaced to the end. The '
             + 'overview page reproduces the same broken ordering, so it does not settle it. They '
             + 'are quoted here rather than answered as requirements.' },
          { quote: 'Discovery & Lifecycle: Agent Registry (the central repository for publishing, '
            + 'versioning, and discovering enterprise-approved agents).\nCore Execution & State: '
            + 'Agent Runtime (for long-running, asynchronous background execution) and Memory Bank '
            + '(for persistent, secure cross-session context over extended timelines).\nSecurity & '
            + 'Governance: Agent Identity (For zero-trust access control), Agent Gateway (for '
            + 'unified routing and policy enforcement), and Model Armor (inline guardrails to block '
            + 'prompt injection, tool poisoning, and PII leaks).\nTelemetry: Agent Observability '
            + '(OpenTelemetry-compliant audit logs and end-to-end reasoning chain traces).\n'
            + 'Recommended Tech to use (Gemini Enterprise Agent Platform):', from: 'Official rules' },
        ] },
      { h: 'Verdict',
        weak: true,
        body: [
          { p: 'Cataloguing, cross-department discovery, and compliance-bounded production data '
             + 'access are the substance of Fortified Enterprise Fleet, and Coroner has none of the '
             + 'three. The multi-agent architecture is genuinely strong and is better argued under '
             + 'Taskmaster’s Architectural Discipline criterion, where it counts for 30% '
             + 'without requiring an enterprise story that does not exist.' },
        ] },
      MANDATORY,
    ],
  },
};

/* The front door needs to explain itself in one screen. */
const PITCH = {
  problem: 'An agent run that crashes leaves an error somebody can alert on. These do not crash. '
         + 'They stop moving and say nothing, and a human only finds out by noticing that nothing '
         + 'has happened for a day.',
  what: 'Coroner is the post-mortem service for that. It takes the JSON a dead run left behind and '
      + 'runs six Gemini 3.5 agents over it: one proposes causes of death, three try to destroy '
      + 'those theories from different angles, one signs the death certificate, one writes the '
      + 'restart plan — and then POSTs that plan back to the orchestrator that lost the run.',
  unprompted: 'Nobody asks for any of it. A scheduled sweep every 15 minutes finds runs that have '
            + 'stopped moving, presumes them dead, and autopsies them unprompted.',
};
