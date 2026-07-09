import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export async function POST(req: Request) {
  try {
    const data = await req.json();

    const deviceId = data.participante || "Desconocido";

    const participant = await prisma.participant.upsert({
      where: { deviceId },
      update: {},
      create: {
        deviceId,
        name: `Participante ${deviceId}`,
      },
    });

    const challengeScore = await prisma.challengeScore.create({
      data: {
        deviceId: participant.deviceId,
        challengeName: data.reto || "Reto Desconocido",
        score: parseFloat(data.puntos) || 0,
        juez: data.juez || "Juez Desconocido",
      },
    });

    return NextResponse.json({ success: true, challengeScore });
  } catch (error) {
    console.error("Error in webhook challenges:", error);
    return NextResponse.json({ error: "Failed to process challenge data" }, { status: 500 });
  }
}
