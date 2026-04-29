"use client";

export function LogoutButton() {
  return (
    <form action="/login">
      <button type="submit" className="button secondary">
        Logout
      </button>
    </form>
  );
}
