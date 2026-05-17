import { expect } from "chai";
import hre from "hardhat";

// Tree built with the SAME convention as MerkleDistributor.sol and
// protocol/merkle.py:
//   leaf = keccak256( keccak256( abi.encode(address, uint256) ) )
//   node = keccak256( sorted(a, b) )
function leafOf(ethers, addr, amount) {
  const enc = ethers.AbiCoder.defaultAbiCoder().encode(
    ["address", "uint256"],
    [addr, amount]
  );
  return ethers.keccak256(ethers.keccak256(enc));
}

function hashPair(ethers, a, b) {
  return BigInt(a) <= BigInt(b)
    ? ethers.keccak256(ethers.concat([a, b]))
    : ethers.keccak256(ethers.concat([b, a]));
}

function buildTree(ethers, entries) {
  const items = [...entries].sort((x, y) =>
    x.addr.toLowerCase() < y.addr.toLowerCase() ? -1 : 1
  );
  const leaves = items.map((e) => leafOf(ethers, e.addr, e.amount));
  const levels = [leaves];
  while (levels[levels.length - 1].length > 1) {
    const cur = levels[levels.length - 1];
    const nxt = [];
    for (let i = 0; i < cur.length; i += 2) {
      nxt.push(i + 1 < cur.length ? hashPair(ethers, cur[i], cur[i + 1]) : cur[i]);
    }
    levels.push(nxt);
  }
  const proofs = {};
  items.forEach((e, idx) => {
    const proof = [];
    let pos = idx;
    for (let l = 0; l < levels.length - 1; l++) {
      const sib = pos ^ 1;
      if (sib < levels[l].length) proof.push(levels[l][sib]);
      pos = Math.floor(pos / 2);
    }
    proofs[e.addr.toLowerCase()] = { amount: e.amount, proof };
  });
  return { root: levels[levels.length - 1][0], proofs };
}

describe("MerkleDistributor", function () {
  this.timeout(60000);

  let conn, ethers;
  let token, dist;
  let deployer, orchestrator, a, b, c;

  before(async function () {
    conn = await hre.network.connect();
    ethers = conn.ethers;
  });

  after(async function () {
    await conn.close();
  });

  beforeEach(async function () {
    [deployer, orchestrator, a, b, c] = await ethers.getSigners();
    const Token = await ethers.getContractFactory("DeAIToken");
    token = await Token.deploy();
    const Dist = await ethers.getContractFactory("MerkleDistributor");
    dist = await Dist.deploy(await token.getAddress(), orchestrator.address);
    const MINTER_ROLE = await token.MINTER_ROLE();
    await token.grantRole(MINTER_ROLE, await dist.getAddress());
  });

  it("only UPDATER_ROLE can publish a root", async function () {
    const { root } = buildTree(ethers, [{ addr: a.address, amount: 100n }]);
    await expect(dist.connect(a).updateRoot(root)).to.be.reverted;
    await expect(dist.connect(orchestrator).updateRoot(root)).to.not.be.reverted;
    expect(await dist.epoch()).to.equal(1n);
  });

  it("lets each miner claim exactly their cumulative amount", async function () {
    const entries = [
      { addr: a.address, amount: ethers.parseEther("10") },
      { addr: b.address, amount: ethers.parseEther("25") },
      { addr: c.address, amount: ethers.parseEther("3") },
    ];
    const { root, proofs } = buildTree(ethers, entries);
    await dist.connect(orchestrator).updateRoot(root);

    await dist.connect(a).claim(proofs[a.address.toLowerCase()].amount, proofs[a.address.toLowerCase()].proof);
    await dist.connect(b).claim(proofs[b.address.toLowerCase()].amount, proofs[b.address.toLowerCase()].proof);
    await dist.connect(c).claim(proofs[c.address.toLowerCase()].amount, proofs[c.address.toLowerCase()].proof);

    expect(await token.balanceOf(a.address)).to.equal(ethers.parseEther("10"));
    expect(await token.balanceOf(b.address)).to.equal(ethers.parseEther("25"));
    expect(await token.balanceOf(c.address)).to.equal(ethers.parseEther("3"));
  });

  it("rejects a double claim with no new earnings", async function () {
    const { root, proofs } = buildTree(ethers, [
      { addr: a.address, amount: ethers.parseEther("10") },
    ]);
    await dist.connect(orchestrator).updateRoot(root);
    const p = proofs[a.address.toLowerCase()];
    await dist.connect(a).claim(p.amount, p.proof);
    await expect(dist.connect(a).claim(p.amount, p.proof)).to.be.revertedWith(
      "MerkleDistributor: nothing to claim"
    );
  });

  it("rejects a bad proof", async function () {
    const { root } = buildTree(ethers, [
      { addr: a.address, amount: ethers.parseEther("10") },
    ]);
    await dist.connect(orchestrator).updateRoot(root);
    await expect(
      dist.connect(a).claim(ethers.parseEther("10"), [])
    ).to.be.revertedWith("MerkleDistributor: bad proof");
    await expect(
      dist.connect(a).claim(ethers.parseEther("999"), [])
    ).to.be.revertedWith("MerkleDistributor: bad proof");
  });

  it("pays only the delta after a cumulative top-up", async function () {
    let t = buildTree(ethers, [{ addr: a.address, amount: ethers.parseEther("10") }]);
    await dist.connect(orchestrator).updateRoot(t.root);
    let p = t.proofs[a.address.toLowerCase()];
    await dist.connect(a).claim(p.amount, p.proof);
    expect(await token.balanceOf(a.address)).to.equal(ethers.parseEther("10"));

    // A earns more → new cumulative root.
    t = buildTree(ethers, [{ addr: a.address, amount: ethers.parseEther("17") }]);
    await dist.connect(orchestrator).updateRoot(t.root);
    p = t.proofs[a.address.toLowerCase()];
    await dist.connect(a).claim(p.amount, p.proof);
    expect(await token.balanceOf(a.address)).to.equal(ethers.parseEther("17"));
    expect(await dist.claimed(a.address)).to.equal(ethers.parseEther("17"));
  });
});
