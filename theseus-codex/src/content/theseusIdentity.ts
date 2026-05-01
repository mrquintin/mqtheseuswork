const signatureClaim = "We put our money where our mind is.";
const contactEmailEnvVar = "NEXT_PUBLIC_THESEUS_CONTACT_EMAIL";
const contactEmailDefault = "hello@theseuscodex.com";

const intellectualCapitalDefinition =
  "Intellectual capital is recorded judgment that can survive criticism, guide action, and compound across decisions. It is not private cleverness; it is thought made durable enough to be inspected, priced, and revised.";

const manifestoBody = `Theseus begins with a refusal to let serious thought dissolve into private conversation. A good argument should not vanish after the meeting ends. A hard-won objection should not be lost because it was inconvenient. A conviction that moves capital should carry the history of how it was formed, what challenged it, and what would defeat it.

We are a group of highly ambitious, future-oriented thinkers from the University of Chicago, united by a commitment to a noble ideal: a better tomorrow. That commitment is not sentimental. It demands methods. It demands records. It demands the discipline to expose our own reasoning to people, tools, markets, and time.

Theseus is a destination for intellectual capital and a vehicle for thoughtful, intentional progress. The Codex is the instrument through which that ambition becomes operational. It records deliberation, extracts claims, preserves dissent, identifies assumptions, and gives every conclusion a memory. It turns the firm's thinking into something durable enough to be searched, attacked, improved, and carried forward into action.

Our organizational axioms are progress, rigor, and intellectual camaraderie. Progress means the future is a responsibility, not an aesthetic. Rigor means assumptions are named, methods are judged, and confidence is earned under pressure. Intellectual camaraderie means we sharpen one another by treating disagreement as a shared instrument rather than a social threat. The dialectic is not ornament; it is how the institution protects itself from comfort.

Frontier technology matters because intelligence can now be made more inspectable, more adversarial, and more cumulative. We use it as an intellectual instrument: to inform investment decisions, to challenge assumptions, and to enact meaningful impact. The tool is not a substitute for judgment. It is a way to make judgment answerable to more evidence, more memory, and more severe tests than unaided conversation can sustain.

But no method deserves reverence until it survives consequence. Theseus therefore treats capital markets as an epistemic arena. Prediction markets force beliefs into probabilities before the world resolves them. Public equities raise the standard further, because capital allocation binds theory to time, uncertainty, and loss. ${signatureClaim} Capital markets are the test our ideas endure.

The firm does not promise infallibility. It promises a stronger standard of failure. When we are wrong, the record should show which premise broke, which method misled us, and what evidence should have changed our minds earlier. Capital outcomes are the falsifiability mechanism for the firm's recorded reasoning. That is the stake: to build an institution whose ideas do not merely sound serious, but endure the audit of reality.`;

export const theseusIdentity = {
  oneLine:
    "A destination for intellectual capital and a vehicle for thoughtful, intentional progress.",
  whatIsTheseus: {
    p1: "Theseus is a group of highly ambitious, future-oriented thinkers from the University of Chicago, united by a commitment to a noble ideal: a better tomorrow. The firm exists as a destination for intellectual capital and a vehicle for thoughtful, intentional progress.",
    p2: "Through the Codex, Theseus records how it reasons, subjects conclusions to adversarial pressure, and converts the strongest surviving judgments into capital-allocation theses. Frontier technology is applied as an intellectual instrument: to inform investment decisions, challenge assumptions, and enact meaningful impact.",
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
    "Theseus treats intellectual capital as recorded judgment under pressure: reasoning that can be challenged, priced, revised, and carried forward. The Codex gives the firm's ideas a memory; markets give them consequence. We put our money where our mind is because capital outcomes are the falsifiability mechanism for the reasoning we choose to record.",
  signatureClaim,
  contactEmailEnvVar,
  contactEmailDefault,
  metadata: {
    title: "Theseus Codex",
    description:
      "A destination for intellectual capital and a vehicle for thoughtful, intentional progress.",
  },
  homePage: {
    identityTitle: "THESEUS",
    commonsLine:
      "This is the firm's public commons. The private workspace lives behind /login.",
  },
  publicHeader: {
    logoAriaLabel:
      "Theseus: a destination for intellectual capital and thoughtful progress.",
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
        title: "Theseus: The Methodological Reorientation",
        href: "https://github.com/mrquintin/mqtheseuswork/blob/main/METHODOLOGICAL_REORIENTATION.md",
      },
      {
        title: "The Meta-Method: Theseus as a Theory of Inquiry",
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
