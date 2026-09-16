export interface SessionVaultPlugin {
  /** Resolves { value: null } if nothing is stored. */
  read(): Promise<{ value: string | null }>;
  /** Rejects if value isn't 32-128 characters. */
  write(options: { value: string }): Promise<void>;
  clear(): Promise<void>;
}

declare const SessionVault: SessionVaultPlugin;
export default SessionVault;
export { SessionVault };
