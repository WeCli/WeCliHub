import crypto from "node:crypto";

import type { NextRequest, NextResponse } from "next/server";

import { SESSION_SECRET } from "@/lib/constants";
import type { GithubUser } from "@/lib/types";

const COOKIE_NAME = "flowhub_session";
const COOKIE_SECURE = process.env.NODE_ENV === "production";
const OAUTH_STATE_MAX_AGE_MS = 10 * 60 * 1000;

type SessionPayload = {
  github_user: GithubUser;
  iat: number;
};

function sign(value: string): string {
  return crypto.createHmac("sha256", SESSION_SECRET).update(value).digest("hex");
}

function encode(payload: SessionPayload): string {
  const base = Buffer.from(JSON.stringify(payload), "utf-8").toString("base64url");
  return `${base}.${sign(base)}`;
}

function decode(token: string): SessionPayload | null {
  const [base, signature] = token.split(".");
  if (!base || !signature) {
    return null;
  }

  if (sign(base) !== signature) {
    return null;
  }

  try {
    const payload = JSON.parse(Buffer.from(base, "base64url").toString("utf-8")) as SessionPayload;
    if (!payload || typeof payload !== "object" || !payload.github_user) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

export function getGithubUser(request: NextRequest): GithubUser | null {
  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (!token) {
    return null;
  }

  const payload = decode(token);
  return payload?.github_user ?? null;
}

export function setGithubUser(response: NextResponse, user: GithubUser): void {
  const token = encode({
    github_user: user,
    iat: Date.now()
  });
  response.cookies.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: COOKIE_SECURE,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 14
  });
}

export function clearGithubUser(response: NextResponse): void {
  response.cookies.set(COOKIE_NAME, "", {
    httpOnly: true,
    secure: COOKIE_SECURE,
    sameSite: "lax",
    path: "/",
    maxAge: 0
  });
}

export function createOauthState(): string {
  const nonce = crypto.randomBytes(24).toString("hex");
  const ts = Date.now().toString();
  const payload = `${nonce}.${ts}`;
  const sig = sign(payload);
  return `${payload}.${sig}`;
}

export function verifyOauthState(state: string | null): boolean {
  if (!state) {
    return false;
  }

  const parts = state.split(".");
  if (parts.length !== 3) {
    return false;
  }

  const [nonce, tsStr, sig] = parts;
  if (!nonce || !tsStr || !sig) {
    return false;
  }

  const ts = Number(tsStr);
  if (!Number.isFinite(ts)) {
    return false;
  }

  const ageMs = Date.now() - ts;
  if (ageMs < 0 || ageMs > OAUTH_STATE_MAX_AGE_MS) {
    return false;
  }

  const expectedSig = sign(`${nonce}.${tsStr}`);
  return sig === expectedSig;
}
