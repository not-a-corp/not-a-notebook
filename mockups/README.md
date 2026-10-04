# Mockups

The visual reference for [design.md](../design.md): the screens at 1440 × 900 in
Light, Dark and Catppuccin Mocha. Start with `not-a-notebook.dc.html` — the
canvas, with the designer's notes at the top — and follow its imports.

They are prototypes, not code. Read them for measures, colours and states; the
app recreates the look, not the structure. They do not open on their own: the
design tool's runtime that renders them is left out.

**design.md prevails.** Where the two disagree, the mockup is the one that is
out of date. Known places:

- Settings → Account offers *Link* and *Unlink*, asks for 12 characters and
  says only an admin changes the email. The API links nothing yet, takes 8 to
  128 characters, and has no admin (§2.7).
- Code comments are lighter than AA allows; design.md darkens them (§5.3).
- The profile drawer lists the CSV separator, which the profile does not carry.
- The sidebar shows a name; the account has only an email (§2.1).
- `Conversation.dc.html` still holds an unused *new* state with a drop zone in
  the chat; a new conversation is the Home screen (§2.3).
- The fonts come from Google Fonts here; the app ships its own (§5.1).
