const signatureClaim =
  "Capital decisions are one way the firm makes its reasoning accountable.";
const contactEmailEnvVar = "NEXT_PUBLIC_THESEUS_CONTACT_EMAIL";
const contactEmailDefault = "hello@theseuscodex.com";

const intellectualCapitalDefinition =
  "Intellectual capital is recorded judgment that can survive criticism, guide action, and compound across decisions. It is not private cleverness; it is thought made durable enough to be inspected, priced, and revised.";

const manifestoBody = `Theseus is building infrastructure for firm reasoning. A useful argument should not disappear when a meeting ends. A serious objection should remain visible after the conversation moves on. A judgment that informs action should retain the record of how it was formed, what challenged it, and what would require revision.

The project begins from a distinction between infrastructure and capital. The infrastructure is replicable: an organization can build a memory layer, require citations, preserve objections, connect conclusions to later evidence, and publish a controlled surface. That portability is part of the point. Intellectual work becomes an industry only when it has tools, protocols, and institutions that many firms can use.

At maturity, this can serve venture firms, research shops, and other knowledge institutions. A partner evaluating an AI forecast, an investment committee testing a thesis, or an executive decision under uncertainty should be able to consult the firm's own accumulated reasoning: documents, meetings, predictions, founder essays, partner debates, and post-mortems. The point is not generic advice. It is live feedback from the firm's recorded mind, used to lower error rates in decisions that matter.

That is close to retrieval-augmented generation with extra discipline, and the manifesto should not mystify it. A context bot embedded in Slack can retrieve useful passages. Theseus is trying to do something more demanding: model the logic of a firm, expose its recurring assumptions, preserve its dissent, and apply that modeled judgment to new situations without pretending that retrieval alone is reasoning.

The value of each installation is therefore its knowledge base, not the software in isolation. A replicated Codex would not reproduce Theseus. It would reveal the mind of the firm using it. A venture firm with manifestos, memos, partner calls, and years of investment debate could build its own Theseus-like system; the resulting model would be valuable precisely because it would not be ours.

This also explains why the need is only now becoming visible. When the actual decision makers are always available, software can seem unnecessary: one can ask the founders, partners, or operators directly. But as firms scale, memory fragments. The same arguments recur, predictions go unscored, private reasoning becomes inaccessible, and the firm loses track of how it came to believe what it believes. The Codex exists to make that collective judgment durable.

For Theseus itself, the model is not merely a consultation surface. The aim is to apply the firm's logic across investing, writing, media production, Currents, prediction-market betting, and any other domain where disciplined judgment can be used profitably. The private Codex is the workspace where the source record is inspected and reprocessed; the public site is a selective publication surface governed by source visibility.

The operating axioms remain progress, rigor, and intellectual camaraderie. Progress means increasing real capability. Rigor means naming assumptions, judging methods, and earning confidence under objection. Intellectual camaraderie means treating disagreement as shared work rather than as a social threat.

No method should be trusted merely because it sounds rigorous. Theseus therefore treats forecasts, market outcomes, and later source evidence as checks on its reasoning. ${signatureClaim} The aim is not infallibility; it is a record detailed enough to show what failed when the firm is wrong.

The standard is operational: when the firm publishes a conclusion, the reader should be able to distinguish the claim, the evidence, the method, the objection, and the conditions for revision. Intellectual capital is human capital made durable without pretending to become post-human. The new industry is not the automation of belief. It is the institutionalization of accountable thought.`;

export const theseusIdentity = {
  oneLine:
    "A working system for recording firm reasoning, testing it, and publishing reviewed perspectives.",
  whatIsTheseus: {
    p1: "Theseus is a research and investment firm building infrastructure for institutional reasoning. The firm records source material, extracts claims and methodology profiles, tests conclusions against objections, and keeps a revision trail for later review.",
    p2: "Through the Codex, founders upload transcripts and writings, inspect the resulting source record, review conclusions, monitor live Currents opinions, and publish selected perspectives without exposing private source material.",
  },
  intellectualCapitalDefinition,
  axioms: [
    {
      name: "Progress",
      elaboration:
        "Progress means the future is a responsibility: we choose projects, questions, and investments by whether they make tomorrow more capable than today.",
    },
    {
      name: "Rigor",
      elaboration:
        "Rigor means first-principles reasoning under pressure: assumptions are named, methods are judged, and confidence is earned only after serious objection.",
    },
    {
      name: "Camaraderie",
      elaboration:
        "Camaraderie means intellectual companionship: a community that challenges assumptions, thinks in fundamental ways, and treats the dialectic as shared work.",
    },
  ] as const,
  manifesto: {
    title: "Manifesto",
    body: manifestoBody,
  },
  manifestoExcerpt:
    "Theseus treats intellectual capital as recorded human judgment under pressure: a firm-owned model of reasoning that can consult on decisions, expose assumptions, and carry institutional memory into new work.",
  signatureClaim,
  contactEmailEnvVar,
  contactEmailDefault,
  metadata: {
    title: "Theseus Codex",
    description:
      "A public surface for Theseus research, Currents opinions, and reviewed firm perspectives.",
  },
  homePage: {
    identityTitle: "THESEUS",
    commonsLine:
      "This public surface shows reviewed articles and Currents opinions. The private workspace lives behind /login.",
  },
  publicHeader: {
    logoAriaLabel:
      "Theseus Codex public home.",
    tagline: "Codex",
  },
  aboutPage: {
    metadataTitle: "About Theseus",
    navAriaLabel: "About page sections",
    sections: [
      { href: "#what", label: "What" },
      { href: "#axioms", label: "Axioms" },
      { href: "#manifesto", label: "Manifesto" },
      { href: "#members", label: "Members" },
      { href: "#contact", label: "Contact" },
    ],
    whatHeading: "What is Theseus?",
    axiomsHeading: "The three axioms.",
  },
  members: {
    heading: "Members.",
    hiddenMessage:
      "The firm currently maintains member anonymity. Reach out via the contact below.",
    emptyMessage:
      "Public member profiles are not yet available. Reach out via the contact below.",
    linkLabel: "Public link",
  },
  contactSection: {
    heading: "Contact.",
    line: "For conversations, guest inquiries, serious objections, or high-signal pitches, reach the firm at",
    disclosure:
      "We read every message. Replies depend on bandwidth; high-signal pitches get priority.",
    form: {
      nameLabel: "Name",
      emailLabel: "Email",
      subjectLabel: "Subject",
      messageLabel: "Message",
      namePlaceholder: "Your name",
      emailPlaceholder: "you@example.com",
      subjectPlaceholder: "Conversation, pitch, objection, or inquiry",
      messagePlaceholder: "Write the highest-signal version of the message.",
      submitLabel: "Send message",
    },
  },
  furtherReading: {
    heading: "Further reading.",
    items: [
      {
        title: "Theseus Methodological Reorientation",
        href: "https://github.com/mrquintin/mqtheseuswork/blob/main/METHODOLOGICAL_REORIENTATION.md",
      },
      {
        title: "The Meta-Method: Working Criteria for Inquiry",
        href: "https://github.com/mrquintin/mqtheseuswork/blob/main/THE_META_METHOD.md",
      },
      {
        title: "Public methodology",
        href: "/methodology",
      },
    ],
  },
} as const;

export function getTheseusContactEmail(): string {
  return (
    process.env[theseusIdentity.contactEmailEnvVar] ??
    theseusIdentity.contactEmailDefault
  );
}
