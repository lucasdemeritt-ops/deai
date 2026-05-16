/**
 * deploy.js — deploys DeAIToken, PaymentContract, SlashingContract
 *
 * Usage:
 *   npx hardhat run scripts/deploy.js                     (local hardhat network)
 *   npx hardhat run scripts/deploy.js --network sepolia   (Sepolia testnet)
 *   npx hardhat run scripts/deploy.js --network amoy      (Polygon Amoy testnet)
 *
 * After deployment the script wires up roles so that:
 *   PaymentContract  → MINTER_ROLE  on DeAIToken
 *   SlashingContract → BURNER_ROLE  on DeAIToken
 */
import hre from "hardhat";

async function main() {
  const conn   = await hre.network.connect();
  const ethers = conn.ethers;

  const [deployer] = await ethers.getSigners();
  console.log(`\nDeploying with account: ${deployer.address}`);
  console.log(`Balance: ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH\n`);

  // ── 1. DeAIToken ────────────────────────────────────────────────
  const Token = await ethers.getContractFactory("DeAIToken");
  const token = await Token.deploy();
  await token.waitForDeployment();
  const tokenAddr = await token.getAddress();
  console.log(`DeAIToken deployed:        ${tokenAddr}`);

  // ── 2. PaymentContract ──────────────────────────────────────────
  // The orchestrator address is the deployer for local dev.
  // On a real network set ORCHESTRATOR_ADDRESS in .env.
  const orchestratorAddr = process.env.ORCHESTRATOR_ADDRESS ?? deployer.address;

  const Payment = await ethers.getContractFactory("PaymentContract");
  const payment = await Payment.deploy(tokenAddr, orchestratorAddr);
  await payment.waitForDeployment();
  const paymentAddr = await payment.getAddress();
  console.log(`PaymentContract deployed:  ${paymentAddr}`);

  // ── 3. SlashingContract ─────────────────────────────────────────
  const Slashing = await ethers.getContractFactory("SlashingContract");
  const slashing = await Slashing.deploy(tokenAddr, orchestratorAddr);
  await slashing.waitForDeployment();
  const slashingAddr = await slashing.getAddress();
  console.log(`SlashingContract deployed: ${slashingAddr}`);

  // ── 4. Wire roles ───────────────────────────────────────────────
  const MINTER_ROLE = await token.MINTER_ROLE();
  const BURNER_ROLE = await token.BURNER_ROLE();

  await (await token.grantRole(MINTER_ROLE, paymentAddr)).wait();
  console.log(`\nGranted MINTER_ROLE → PaymentContract`);

  await (await token.grantRole(BURNER_ROLE, slashingAddr)).wait();
  console.log(`Granted BURNER_ROLE → SlashingContract`);

  // ── 5. Summary ──────────────────────────────────────────────────
  console.log(`
────────────────────────────────────────────────
  DEPLOYMENT COMPLETE
────────────────────────────────────────────────
  Network:          ${conn.networkName}
  Orchestrator:     ${orchestratorAddr}

  DeAIToken:        ${tokenAddr}
  PaymentContract:  ${paymentAddr}
  SlashingContract: ${slashingAddr}
────────────────────────────────────────────────

  Save these addresses — you'll need them to configure
  the orchestrator and any front-end or explorer tools.
`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
