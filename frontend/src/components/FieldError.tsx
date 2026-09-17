/** Validation messages for one form field, rendered only when the server returns some. */
export function FieldError({ id, messages }: { id?: string; messages?: string[] }) {
  if (!messages?.length) return null;
  return (
    <p id={id} className="field-error">
      {messages.join(" ")}
    </p>
  );
}
