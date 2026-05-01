"use client";

import { useRef, useState, type FormEvent } from "react";

type ContactFormCopy = {
  nameLabel: string;
  emailLabel: string;
  subjectLabel: string;
  messageLabel: string;
  namePlaceholder: string;
  emailPlaceholder: string;
  subjectPlaceholder: string;
  messagePlaceholder: string;
  submitLabel: string;
};

type FieldErrors = Partial<
  Record<"fromName" | "fromEmail" | "subject" | "body", string>
>;

type ContactResponse = {
  ok?: boolean;
  error?: string;
  fieldErrors?: FieldErrors;
};

const honeypotStyle = {
  height: "1px",
  left: "-10000px",
  overflow: "hidden",
  position: "absolute",
  top: "auto",
  width: "1px",
} as const;

export default function ContactForm({
  contactEmail,
  disclosure,
  form,
}: {
  contactEmail: string;
  disclosure: string;
  form: ContactFormCopy;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const currentForm = event.currentTarget;
    setSubmitting(true);
    setStatusMessage("");
    setFieldErrors({});

    try {
      const res = await fetch(currentForm.action, {
        method: currentForm.method,
        body: new FormData(currentForm),
        headers: { Accept: "application/json" },
      });
      const payload = (await res.json().catch(() => ({}))) as ContactResponse;

      if (res.ok && payload.ok) {
        formRef.current?.reset();
        setStatusMessage("Received. The firm will read this within ~7 days.");
        return;
      }

      setFieldErrors(payload.fieldErrors || {});
      setStatusMessage(
        payload.error ||
          "The message could not be received. Check the fields and try again.",
      );
    } catch (error) {
      setStatusMessage(
        error instanceof Error
          ? error.message
          : "The message could not be received. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <form
        action="/api/contact"
        className="public-card public-form-card"
        method="post"
        noValidate
        onSubmit={handleSubmit}
        ref={formRef}
        style={{
          display: "grid",
          gap: "0.85rem",
          maxWidth: "42rem",
        }}
      >
        <label className="public-label" htmlFor="contact-from-name">
          {form.nameLabel}
          <input
            aria-describedby={
              fieldErrors.fromName ? "contact-from-name-error" : undefined
            }
            aria-invalid={fieldErrors.fromName ? "true" : undefined}
            autoComplete="name"
            id="contact-from-name"
            maxLength={100}
            name="fromName"
            placeholder={form.namePlaceholder}
            required
            type="text"
          />
        </label>
        {fieldErrors.fromName ? (
          <p className="public-field-error" id="contact-from-name-error">
            {fieldErrors.fromName}
          </p>
        ) : null}

        <label className="public-label" htmlFor="contact-from-email">
          {form.emailLabel}
          <input
            aria-describedby={
              fieldErrors.fromEmail ? "contact-from-email-error" : undefined
            }
            aria-invalid={fieldErrors.fromEmail ? "true" : undefined}
            autoComplete="email"
            id="contact-from-email"
            maxLength={254}
            name="fromEmail"
            placeholder={form.emailPlaceholder}
            required
            type="email"
          />
        </label>
        {fieldErrors.fromEmail ? (
          <p className="public-field-error" id="contact-from-email-error">
            {fieldErrors.fromEmail}
          </p>
        ) : null}

        <label className="public-label" htmlFor="contact-subject">
          {form.subjectLabel}
          <input
            aria-describedby={
              fieldErrors.subject ? "contact-subject-error" : undefined
            }
            aria-invalid={fieldErrors.subject ? "true" : undefined}
            id="contact-subject"
            maxLength={200}
            name="subject"
            placeholder={form.subjectPlaceholder}
            type="text"
          />
        </label>
        {fieldErrors.subject ? (
          <p className="public-field-error" id="contact-subject-error">
            {fieldErrors.subject}
          </p>
        ) : null}

        <label className="public-label" htmlFor="contact-body">
          {form.messageLabel}
          <textarea
            aria-describedby={
              fieldErrors.body ? "contact-body-error" : undefined
            }
            aria-invalid={fieldErrors.body ? "true" : undefined}
            id="contact-body"
            maxLength={4000}
            minLength={10}
            name="body"
            placeholder={form.messagePlaceholder}
            required
            rows={5}
          />
        </label>
        {fieldErrors.body ? (
          <p className="public-field-error" id="contact-body-error">
            {fieldErrors.body}
          </p>
        ) : null}

        <div aria-hidden="true" style={honeypotStyle}>
          <label htmlFor="contact-company-url">Company URL</label>
          <input
            autoComplete="off"
            id="contact-company-url"
            name="company_url"
            tabIndex={-1}
            type="text"
          />
        </div>

        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.85rem",
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          {disclosure}
        </p>

        <div
          aria-live="polite"
          className="public-form-status"
          role="status"
        >
          {statusMessage}
        </div>

        <button
          className="btn btn-solid"
          disabled={submitting}
          style={{ justifySelf: "start" }}
          type="submit"
        >
          {submitting ? "Sending..." : form.submitLabel}
        </button>
      </form>

      <p
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.95rem",
          lineHeight: 1.5,
          marginTop: "0.85rem",
        }}
      >
        or email us directly at{" "}
        <a
          href={`mailto:${contactEmail}`}
          style={{ color: "var(--amber)", textDecoration: "none" }}
        >
          {contactEmail}
        </a>
        .
      </p>
    </>
  );
}
