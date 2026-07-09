import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export async function POST(req: Request) {
  try {
    const data = await req.json();

    const deviceId = data.participante || "Desconocido";

    const participant = await prisma.participant.upsert({
      where: { deviceId },
      update: {
        pesoKg: data.carga_kg,
        team: data.equipo,
      },
      create: {
        deviceId,
        name: `Participante ${deviceId}`,
        team: data.equipo,
        pesoKg: data.carga_kg,
      },
    });

    const scanLog = await prisma.scanLog.create({
      data: {
        deviceId: participant.deviceId,
        pesoDetectadoKg: data.carga_kg,
        rojoCount: data.roja || 0,
        blancoCount: data.blanca || 0,
        negroCount: data.negra || 0,
        juez: data.juez,
        checkpointId: data.checkpoint ? parseInt(data.checkpoint.replace(/\D/g, "")) || null : null,
      },
    });

    return NextResponse.json({ success: true, scanLog });
  } catch (error) {
    console.error("Error in webhook scan:", error);
    return NextResponse.json({ error: "Failed to process scan data" }, { status: 500 });
  }
}
