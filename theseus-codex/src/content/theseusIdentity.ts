const signatureClaim =
  "Capital decisions are one way the firm makes its reasoning accountable.";
const contactEmailEnvVar = "NEXT_PUBLIC_THESEUS_CONTACT_EMAIL";
const contactEmailDefault = "hello@theseuscodex.com";

const intellectualCapitalDefinition =
  "Intellectual capital is recorded judgment that can survive criticism, guide action, and compound across decisions. It is not private cleverness; it is thought made durable enough to be inspected, priced, and revised.";

const manifestoBody = `Theseus is building infrastructure for firm reasoning. A useful argument should not disappear when a meeting ends. A serious objection should remain visible after the conversation moves on. A judgment that informs action should retain the record of how it was formed, what challenged it, and what would require revision.

The firm is organized around a practical claim: reasoning improves when it is recorded, criticized, compared against alternatives, and later checked against consequences. That claim is methodological rather than sentimental. It requires source records, explicit assumptions, public/private boundaries, and a willingness to let evidence change the result.

The Codex is the operating surface for that work. It records deliberation, processes uploaded source material, extracts conclusions, preserves dissent, identifies methodological patterns, and gives each reviewed judgment a traceable history. Currents and public articles expose a narrower surface: the firm's perspective on live events and selected conclusions, with citations governed by source visibility.

The operating axioms are progress, rigor, and intellectual camaraderie. Progress means choosing work by whether it increases real capability. Rigor means naming assumptions, judging methods, and earning confidence under objection. Intellectual camaraderie means treating disagreement as shared work rather than as a social threat.

Frontier technology matters here because it can make reasoning more inspectable, adversarial, and cumulative. It is not treated as a substitute for judgment. It is used to preserve records, retrieve relevant sources, test objections, and make later review easier than unaided conversation would allow.

No method should be trusted merely because it sounds rigorous. Theseus therefore treats forecasts, market outcomes, and later source evidence as checks on its reasoning. ${signatureClaim} The aim is not infallibility; it is a record detailed enough to show what failed when the firm is wrong.

The standard is operational: when the firm publishes a conclusion, the reader should be able to distinguish the claim, the evidence, the method, the objection, and the conditions for revision. The public site is a selective publication surface, not a dump of private sources. The private Codex remains the workspace where the source record can be inspected and reprocessed.`;

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
    "Theseus treats intellectual capital as recorded judgment under pressure: reasoning that can be challenged, revised, and carried forward. The Codex gives the firm's ideas a memory; forecasts, market outcomes, and later source evidence give them consequence.",
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
