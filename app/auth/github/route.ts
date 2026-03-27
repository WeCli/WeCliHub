import { NextRequest, NextResponse } from "next/server";

import { createOauthState } from "@/lib/auth";
import { GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET } from "@/lib/constants";
import { resolveGithubRedirectUri } from "@/lib/oauth";

export async function GET(request: NextRequest) {
  if (!GITHUB_CLIENT_ID || !GITHUB_CLIENT_SECRET) {
    return NextResponse.json(
      {
        error: "GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET environment variables."
      },
      { status: 500 }
    );
  }

  const state = createOauthState();
  const redirectUri = resolveGithubRedirectUri(request);
  const githubAuthUrl = new URL("https://github.com/login/oauth/authorize");
  githubAuthUrl.searchParams.set("client_id", GITHUB_CLIENT_ID);
  githubAuthUrl.searchParams.set("redirect_uri", redirectUri);
  githubAuthUrl.searchParams.set("scope", "read:user");
  githubAuthUrl.searchParams.set("state", state);

  return NextResponse.redirect(githubAuthUrl.toString());
}
