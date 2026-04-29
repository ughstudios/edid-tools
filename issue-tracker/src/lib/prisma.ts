import { PrismaClient } from "@prisma/client";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryableConnectionError(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e);
  return /P1017|P1001|P1002|P1008|Kind:\s*Closed|closed the connection|Connection terminated|ECONNRESET|ETIMEDOUT|EPIPE/i.test(
    msg,
  );
}

function createExtendedClient() {
  const base = new PrismaClient({
    log: process.env.NODE_ENV === "development" ? ["warn", "error"] : ["error"],
  });

  return base.$extends({
    query: {
      async $allOperations({ args, query }) {
        const maxAttempts = 3;
        let lastError: unknown;
        for (let attempt = 0; attempt < maxAttempts; attempt++) {
          try {
            return await query(args);
          } catch (e) {
            lastError = e;
            if (!isRetryableConnectionError(e) || attempt === maxAttempts - 1) {
              throw e;
            }
            await sleep(75 * (attempt + 1));
          }
        }
        throw lastError;
      },
    },
  });
}

type ExtendedPrisma = ReturnType<typeof createExtendedClient>;

const globalForPrisma = globalThis as unknown as { prisma?: ExtendedPrisma };

export const prisma: ExtendedPrisma = globalForPrisma.prisma ?? createExtendedClient();

/** Always reuse one client per runtime (dev HMR + Vercel isolates) to avoid stale pools and connection spikes. */
globalForPrisma.prisma = prisma;
