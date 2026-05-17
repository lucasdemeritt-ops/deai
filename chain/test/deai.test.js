import { expect } from "chai";
import hre from "hardhat";

describe("DeAI Contract Suite", function () {
  this.timeout(60000);

  let conn, ethers;
  let token, payment, slashing;
  let deployer, orchestrator, user, miner, miner2;
  let INITIAL_STAKE, SLASH_AMOUNT, MINER_BONUS, TASK_PAYMENT;
  let TASK_ID, TASK_HASH;
  const TTL = 3600;

  before(async function () {
    conn   = await hre.network.connect();
    ethers = conn.ethers;

    INITIAL_STAKE = ethers.parseEther("100");
    SLASH_AMOUNT  = ethers.parseEther("10");
    MINER_BONUS   = ethers.parseEther("10");
    TASK_PAYMENT  = ethers.parseEther("5");
    TASK_ID       = ethers.encodeBytes32String("task-001");
    TASK_HASH     = ethers.keccak256(ethers.toUtf8Bytes("what is 2+2?"));
  });

  after(async function () {
    await conn.close();
  });

  beforeEach(async function () {
    [deployer, orchestrator, user, miner, miner2] = await ethers.getSigners();

    const Token    = await ethers.getContractFactory("DeAIToken");
    const Payment  = await ethers.getContractFactory("PaymentContract");
    const Slashing = await ethers.getContractFactory("SlashingContract");

    token    = await Token.deploy();
    payment  = await Payment.deploy(await token.getAddress(), orchestrator.address);
    slashing = await Slashing.deploy(await token.getAddress(), orchestrator.address);

    const MINTER_ROLE = await token.MINTER_ROLE();
    const BURNER_ROLE = await token.BURNER_ROLE();
    await token.grantRole(MINTER_ROLE, await payment.getAddress());
    await token.grantRole(BURNER_ROLE, await slashing.getAddress());

    // Deployer gets MINTER_ROLE for funding test wallets
    await token.grantRole(MINTER_ROLE, deployer.address);
    await token.mint(user.address,   ethers.parseEther("1000"));
    await token.mint(miner.address,  ethers.parseEther("500"));
    await token.mint(miner2.address, ethers.parseEther("500"));
  });

  // ─────────────────────────────────────────────────────────────────
  // DeAIToken
  // ─────────────────────────────────────────────────────────────────
  describe("DeAIToken", function () {
    it("mints tokens to an authorized address", async function () {
      const before = await token.balanceOf(user.address);
      await token.mint(user.address, ethers.parseEther("50"));
      expect(await token.balanceOf(user.address)).to.equal(before + ethers.parseEther("50"));
    });

    it("rejects mint from unauthorized caller", async function () {
      try {
        await token.connect(user).mint(user.address, ethers.parseEther("1"));
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.not.equal("expected revert");
      }
    });

    it("burns tokens from an authorized burner", async function () {
      const burnAmt = ethers.parseEther("10");
      const before  = await token.balanceOf(user.address);
      const BURNER_ROLE = await token.BURNER_ROLE();
      await token.grantRole(BURNER_ROLE, deployer.address);
      await token.burn(user.address, burnAmt);
      expect(await token.balanceOf(user.address)).to.equal(before - burnAmt);
    });

    it("rejects burn from unauthorized caller", async function () {
      try {
        await token.connect(user).burn(user.address, ethers.parseEther("1"));
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.not.equal("expected revert");
      }
    });
  });

  // ─────────────────────────────────────────────────────────────────
  // SlashingContract
  // ─────────────────────────────────────────────────────────────────
  describe("SlashingContract", function () {
    beforeEach(async function () {
      await token.connect(miner).approve(await slashing.getAddress(), INITIAL_STAKE);
      await slashing.connect(miner).stake(INITIAL_STAKE);
    });

    it("records stake correctly", async function () {
      const record = await slashing.miners(miner.address);
      expect(record.stake).to.equal(INITIAL_STAKE);
      expect(record.ejected).to.equal(false);
    });

    it("is eligible after staking", async function () {
      expect(await slashing.isEligible(miner.address)).to.equal(true);
    });

    it("is eligible even without stake — no barrier to entry", async function () {
      expect(await slashing.isEligible(miner2.address)).to.equal(true);
    });

    it("recordCompletion increments tasksCompleted", async function () {
      await slashing.connect(orchestrator).recordCompletion(miner.address);
      const record = await slashing.miners(miner.address);
      expect(record.tasksCompleted).to.equal(1n);
    });

    it("slash reduces stake and increments timesSlashed", async function () {
      await slashing.connect(orchestrator).slash(miner.address);
      const record = await slashing.miners(miner.address);
      expect(record.stake).to.equal(INITIAL_STAKE - SLASH_AMOUNT);
      expect(record.timesSlashed).to.equal(1n);
    });

    it("slash ejects miner when stake is fully burned", async function () {
      for (let i = 0; i < 10; i++) {
        const rec = await slashing.miners(miner.address);
        if (!rec.ejected) await slashing.connect(orchestrator).slash(miner.address);
      }
      const record = await slashing.miners(miner.address);
      expect(record.ejected).to.equal(true);
    });

    it("slash ejects a zero-stake miner on first offense", async function () {
      // miner2 has no stake at all
      await slashing.connect(orchestrator).slash(miner2.address);
      const record = await slashing.miners(miner2.address);
      expect(record.ejected).to.equal(true);
      expect(record.timesSlashed).to.equal(1n);
    });

    it("ejected miner cannot rejoin by staking again", async function () {
      for (let i = 0; i < 10; i++) {
        const rec = await slashing.miners(miner.address);
        if (!rec.ejected) await slashing.connect(orchestrator).slash(miner.address);
      }
      await token.connect(miner).approve(await slashing.getAddress(), INITIAL_STAKE);
      try {
        await slashing.connect(miner).stake(INITIAL_STAKE);
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.include("Ejected miners cannot rejoin");
      }
    });

    it("withdrawStake lets miner pull excess above MIN_STAKE", async function () {
      const extra = ethers.parseEther("50");
      await token.connect(miner).approve(await slashing.getAddress(), extra);
      await slashing.connect(miner).stake(extra);

      const before = await token.balanceOf(miner.address);
      await slashing.connect(miner).withdrawStake(extra);
      expect(await token.balanceOf(miner.address)).to.equal(before + extra);
    });

    it("withdrawStake rejects dropping below MIN_STAKE", async function () {
      try {
        await slashing.connect(miner).withdrawStake(ethers.parseEther("1"));
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.include("Cannot drop below minimum stake while active");
      }
    });

    it("exitNetwork returns all stake and ejects miner", async function () {
      const before = await token.balanceOf(miner.address);
      await slashing.connect(miner).exitNetwork();
      expect(await token.balanceOf(miner.address)).to.equal(before + INITIAL_STAKE);
      const record = await slashing.miners(miner.address);
      expect(record.ejected).to.equal(true);
      expect(record.stake).to.equal(0n);
    });

    it("only orchestrator can slash", async function () {
      try {
        await slashing.connect(user).slash(miner.address);
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.not.equal("expected revert");
      }
    });
  });

  // ─────────────────────────────────────────────────────────────────
  // PaymentContract
  // ─────────────────────────────────────────────────────────────────
  describe("PaymentContract", function () {
    beforeEach(async function () {
      await token.connect(user).approve(await payment.getAddress(), TASK_PAYMENT);
      await payment.connect(user).depositAndRequest(
        TASK_ID, TASK_HASH, miner.address, TASK_PAYMENT, TTL
      );
    });

    it("locks tokens in escrow on deposit", async function () {
      const task = await payment.tasks(TASK_ID);
      expect(task.amount).to.equal(TASK_PAYMENT);
      expect(task.completed).to.equal(false);
      expect(task.user).to.equal(user.address);
    });

    it("completeTask pays miner and mints bonus", async function () {
      const before = await token.balanceOf(miner.address);
      await payment.connect(orchestrator).completeTask(TASK_ID);
      const after  = await token.balanceOf(miner.address);
      expect(after).to.equal(before + TASK_PAYMENT + MINER_BONUS);
    });

    it("completeTask marks task as completed", async function () {
      await payment.connect(orchestrator).completeTask(TASK_ID);
      const task = await payment.tasks(TASK_ID);
      expect(task.completed).to.equal(true);
    });

    it("cannot complete a task twice", async function () {
      await payment.connect(orchestrator).completeTask(TASK_ID);
      try {
        await payment.connect(orchestrator).completeTask(TASK_ID);
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.include("Already completed");
      }
    });

    it("refund returns tokens after deadline", async function () {
      await conn.provider.send("evm_increaseTime", [TTL + 1]);
      await conn.provider.send("evm_mine", []);

      const before = await token.balanceOf(user.address);
      await payment.connect(user).refund(TASK_ID);
      expect(await token.balanceOf(user.address)).to.equal(before + TASK_PAYMENT);
    });

    it("refund rejected before deadline", async function () {
      try {
        await payment.connect(user).refund(TASK_ID);
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.include("Task not yet timed out");
      }
    });

    it("refund rejected for wrong caller", async function () {
      await conn.provider.send("evm_increaseTime", [TTL + 1]);
      await conn.provider.send("evm_mine", []);
      try {
        await payment.connect(miner).refund(TASK_ID);
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.include("Not your task");
      }
    });

    it("cannot deposit duplicate task ID", async function () {
      await token.connect(user).approve(await payment.getAddress(), TASK_PAYMENT);
      try {
        await payment.connect(user).depositAndRequest(TASK_ID, TASK_HASH, miner.address, TASK_PAYMENT, TTL);
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.include("Task already exists");
      }
    });

    it("only orchestrator can call completeTask", async function () {
      try {
        await payment.connect(user).completeTask(TASK_ID);
        expect.fail("expected revert");
      } catch (e) {
        expect(e.message).to.not.equal("expected revert");
      }
    });
  });
});
