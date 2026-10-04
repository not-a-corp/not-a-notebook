// The API names no field when it refuses one (a 422 never repeats the input), so
// the form checks what api.md documents before sending, and says it on the field.

export interface FieldErrors {
  email?: string;
  password?: string;
}

export function validateCredentials(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};

  if (!email.includes("@")) {
    errors.email = "Enter an email address.";
  }

  if (password.length < 8) {
    errors.password = "At least 8 characters.";
  }

  if (password.length > 128) {
    errors.password = "At most 128 characters.";
  }

  return errors;
}

export function hasErrors(errors: FieldErrors): boolean {
  return errors.email !== undefined || errors.password !== undefined;
}
