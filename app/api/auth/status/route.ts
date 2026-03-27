import { NextRequest, NextResponse } from "next/server";

import { getGithubUser } from "@/lib/auth";
import { GITHUB_CLIENT_ID } from "@/lib/constants";

export async function GET(request: NextRequest) {
  const user = getGithubUser(request);
  if (user) {
    return NextResponse.json({ logged_in: true, user });
  }

  return NextResponse.json({ logged_in: false, github_client_id: GITHUB_CLIENT_ID || null });
}
