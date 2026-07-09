import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export async function GET() {
  try {
    const participants = await prisma.participant.findMany({
      include: {
        telemetryLogs: {
          orderBy: { timestamp: 'desc' },
          take: 1,
        },
        challengeScores: true,
        scanLogs: {
          orderBy: { timestamp: 'desc' },
          take: 1,
        }
      },
      orderBy: { createdAt: 'desc' }
    });

    return NextResponse.json(participants);
  } catch (error) {
    console.error("Error fetching participants:", error);
    return NextResponse.json({ error: "Failed to fetch data" }, { status: 500 });
  }
}
