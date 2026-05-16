import hardhatEthers from "@nomicfoundation/hardhat-ethers";
import { config as dotenvConfig } from "dotenv";

dotenvConfig();

/** @type import('hardhat/config').HardhatUserConfig */
export default {
  plugins: [hardhatEthers],
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    // Local in-memory chain — free, instant, no setup
    hardhat: { type: "edr-simulated" },
    // Testnet entries added here when ready to deploy (see .env.example)
    ...(process.env.SEPOLIA_RPC_URL ? {
      sepolia: { type: "http", url: process.env.SEPOLIA_RPC_URL, accounts: [process.env.DEPLOYER_PRIVATE_KEY] },
    } : {}),
    ...(process.env.AMOY_RPC_URL ? {
      amoy: { type: "http", url: process.env.AMOY_RPC_URL, accounts: [process.env.DEPLOYER_PRIVATE_KEY] },
    } : {}),
  },
};
