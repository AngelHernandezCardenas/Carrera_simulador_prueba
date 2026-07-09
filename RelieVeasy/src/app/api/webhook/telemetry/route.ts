import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export async function POST(req: Request) {
  try {
    const data = await req.json();

    const deviceId = data.device_id || "Desconocido";

    const participant = await prisma.participant.upsert({
      where: { deviceId },
      update: {
        name: data.participante || undefined,
      },
      create: {
        deviceId,
        name: data.participante || `Participante ${deviceId}`,
      },
    });

    const telemetryLog = await prisma.telemetryLog.create({
      data: {
        deviceId: participant.deviceId,
        lat: data.latitude,
        lon: data.longitude,
        speedKmh: data.speed_kmh,
        battery: data.nivel_bateria,
      },
    });

    return NextResponse.json({ success: true, telemetryLog });
  } catch (error) {
    console.error("Error in webhook telemetry:", error);
    return NextResponse.json({ error: "Failed to process telemetry data" }, { status: 500 });
  }
}
