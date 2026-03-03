# DocVerify Evaluation Report
**Generated:** 2026-03-03T12:58:05.749749
**Tenant:** default

## Summary

| Question | Loop | Overall | Correctness | Verdict |
|----------|------|---------|-------------|---------|
| Q1 | A | 0.86 | 0.91 | ✅ PASS |
| Q2 | A | 0.76 | 0.81 | ❌ FAIL |
| Q3 | A | 0.81 | 0.91 | ✅ PASS |

**Total time:** 414.9s

---
## Q1: Why does the highly peer-to-peer design of the DDC clusters ensure resilience? A...

### Answer

# Why DDC's Peer-to-Peer Design Ensures Resilience and Suits Autonomous Edge/Hybrid Enterprise Clusters

## Direct Answer

DDC's peer-to-peer design ensures resilience through data redundancy (replication and erasure coding), automatic routing around failed nodes, and a data repair mechanism that redistributes data when nodes leave the cluster. It is suitable for autonomous edge or hybrid enterprise clusters because each DDC cluster operates as a "complete, independent cloud" that can function even when blockchain connectivity is unavailable, with configurable redundancy parameters and the ability to optimize clusters for specific data types and regions.

## Detailed Explanation

### Resilience Through P2P Architecture

DDC Core is described as "the foundational software suite for DDC nodes within the Cere Network" that "enables individual nodes to join a cluster and collaborate" [[chunk:p1-0054]]. Each node is "an isolated piece of software that can join to the network with other nodes" [[chunk:p2-0055]], and each Storage Node "is connected to Cere Blockchain, listens for the changes in cluster topology and reacts to it by updating caches, access policy or network topology" [[chunk:p2-0055]].

The resilience mechanism is grounded in data redundancy. Data is "distributed across multiple nodes using two strategies: Small pieces: Replication (multiple copies)" and "Pieces larger than 16 KB: Erasure coding" [[chunk:p2-0022]]. When nodes fail, the system handles it in two ways: "Temporary outage: System routes around failures automatically" and "Permanent loss: Data survives if enough copies/shares remain" [[chunk:p2-0022]]. Erasure coding specifically works by encoding data into N shares where "only any K of them are required to recover the original block of data," and "erasure codes can increase durability without increasing the expansion factor" because "the risk is spread across more nodes" [[chunk:p2-0038]].

The peer-to-peer repair mechanism is demonstrated by simulation: when a node is removed from the cluster, "part of metadata stored on that node was distributed across other nodes and also segments/merkle trees were successfully repaired and stored on other nodes." Furthermore, after a node leaves, "other nodes (p2p communication) don't send requests to the failed node" [[chunk:p19-0064]]. The node removal process includes on-chain removal, P2P authentication blocking the removed node, and repair being triggered across remaining nodes [[chunk:p19-0064]].

The system also uses DHT (Distributed Hash Table) for node discovery, configured with a replication factor of 5, key space length of 256, and concurrency of 3. Nodes "get list of nodes from smart contract on startup" and use discovered nodes as DHT bootstrap nodes [[chunk:p10-0060]].

The non-functional requirements explicitly state: "Client data is always available even when a node (or multiple nodes) leave a network" and "Storage protocol guarantees the required level of durability (e.g. 99.99999%) and tolerates node shutdowns (both expected and unexpected) or any misbehaviour" [[chunk:p35-0070]].

### Suitability for Autonomous Edge/Hybrid Enterprise Clusters

Each DDC cluster is described as "a complete, independent cloud. It replaces traditional infrastructure like VPC, S3, and compute services in one decentralized system with built-in on-chain verification" [[chunk:p2-0022]]. This unified stack means "instead of stitching together S3 + CloudFront + Lambda + custom metering, you get a unified stack where every operation is auditable and verified on-chain" [[chunk:p2-0022]].

A critical capability for autonomous operation is blockchain-independent resilience. Milestone 3.5 specifically addresses this: "Storage and cache nodes are using nodes index that is persisted on disk. So that even in case blockchain is unavailable, they can be restarted and function without any errors" [[chunk:p32-0069]]. Similarly, the authentication gater is designed so that "even in case blockchain is unavailable, and customer information isn't in cache (or nodes were restarted), the node is able to authenticate the client so the storage and cache can handle clients requests and service availability from client perspective is increased" [[chunk:p32-0069]].

For enterprise edge deployment, DDC supports "Regional & Industry Optimization: Tailor clusters for low-latency transactional data (e.g., New Zealand) or high-bandwidth video streaming (e.g., Central Asia)" [[chunk:p2-0022]]. The architecture enables "Edge-Native AI: Moves compute to the data rather than data to the cloud, reducing latency and enabling autonomous, real-time agentic workflows" [[chunk:p2-0022]].

The system also offers "Separation of Cloud Infra & Operations: The tools and services offered by Cere ensure a clean separation of cloud infrastructure & operations from the protocol. This unique separation allows specialized data to reside on the edge, while also ensuring seamless integration and interoperability through the Cere L1 Blockchain and smart contracts" [[chunk:p4-0023]].

DDC clusters support configurable SLAs — smaller clusters (e.g., 5 nodes) can be created with custom redundancy parameters including "replication factor, erasure coding total/required" and "success/repair thresholds" set on-chain [[chunk:p30-0068]]. This configurability enables enterprises to deploy appropriately sized clusters at the edge.

The protocol is designed to accept untrusted nodes with security protections: "Internal communication is protected against malicious activity. Each operation is authorized... Data transferred internally is authenticated by hashes." The acceptance criterion is that "Malicious node providers can't increase their income in a dishonest way (e.g. generate invalid activity report) or hurt the cluster (pollute the network, corrupt data etc.)" [[chunk:p32-0069]].

For data security in enterprise contexts, "DDC uses erasure coding to distribute your data across multiple nodes in the cluster... Data is split into fragments, with each node storing only a portion of your files. For a malicious actor to reconstruction a file, they require control over a significant portion of the cluster" [[chunk:p4-0023]]. Client-side encryption is also available for sensitive data [[chunk:p4-0023]].

## Planned/Roadmap Items

- **Proof of storage auditing**: "The protocol ensures that data is stored over time. In case some data was lost or malicious nodes didn't store it at all, protocol should be able to detect it, report... and repair data in case it's needed" — this is described as a milestone deliverable [[chunk:p32-0069]].
- **SDK-integrated key management**: "Client-side encryption is available manually. SDK-integrated key management with delegated access grants is in development" [[chunk:p4-0023]].
- **Compute cost metrics**: As a planned capability, "The cost metrics need to be clearly defined to determine how much an agent or customer should be charged for compute usage" [[chunk:p2-0022]].

## What the Documents Do NOT Cover

- The documents do not provide a formal definition of "highly peer-to-peer design" as a specific architectural term or explain exactly how DDC's P2P topology differs from partially P2P or hub-and-spoke designs.
- The documents do not provide specific latency or recovery time benchmarks for the repair mechanism after node failure.
- The documents do not detail how "hybrid cluster" configurations work (combining on-premises edge nodes with cloud-hosted nodes).
- Key loss scenarios for client-side encryption are not addressed in the provided evidence.

## DOC_GAPS — Documentation Improvement Recommendations

- **GAP**: No explicit documentation characterizing DDC's architecture as "highly peer-to-peer" or explaining the specific P2P topology (full mesh, structured overlay, etc.) and why that topology enhances resilience compared to alternatives.
 - **IMPLICATION**: The evidence implies full peer-to-peer communication (DHT, direct node-to-node repair) but never formally labels or defines the topology.
 - **RECOMMENDATION**: Add an architecture overview section to DDC Core Wiki explicitly describing the P2P topology, how nodes discover and communicate with each other, and why this design provides resilience advantages.

- **GAP**: No documentation on "hybrid cluster" deployment models combining edge and cloud nodes within a single cluster.
 - **IMPLICATION**: The docs discuss edge-native deployment and regional clusters separately but do not describe a hybrid model.
 - **RECOMMENDATION**: Add a deployment patterns guide covering hybrid edge-cloud cluster configurations, including network topology requirements and failover behavior.

- **GAP**: No documentation on key loss implications for client-side encrypted data.
 - **IMPLICATION**: The docs state client-side encryption is available but do not address what happens if encryption keys are lost.
 - **RECOMMENDATION**: Add a section on key management best practices and key loss consequences to the data security documentation.

- **GAP**: Repair mechanism simulation revealed issues (metrics skew, CDN nodes incorrectly triggering repair) but no documentation confirms these were resolved.
 - **IMPLICATION**: The chaos engineering simulation at [[chunk:p19-0064]] identified bugs; resolution status is unclear.
 - **RECOMMENDATION**: Update the chaos engineering results with resolution status for each identified issue.

## Citations Summary

- [[chunk:p1-0054]] — DDC Core description, node collaboration
- [[chunk:p2-0055]] — Node isolation, blockchain connectivity, topology updates
- [[chunk:p2-0022]] — DDC as independent cloud, redundancy strategies, failure handling, edge-native AI
- [[chunk:p2-0038]] — Erasure coding mechanics, durability comparison
- [[chunk:p19-0064]] — Node leaving simulation, repair mechanism behavior
- [[chunk:p10-0060]] — DHT configuration, node discovery
- [[chunk:p35-0070]] — Non-functional requirements: availability, durability guarantees
- [[chunk:p32-0069]] — Blockchain-independent operation, untrusted nodes, configurable SLAs
- [[chunk:p30-0068]] — Configurable redundancy parameters, smaller cluster support
- [[chunk:p4-0023]] — Data distribution security, client-side encryption, separation of infra and operations

### Scores

- **grounded_correctness:** 0.91
- **completeness:** 0.95
- **precision:** 0.70
- **clarity:** 0.90
- **citation_quality:** 0.78
- **Overall:** 0.86

---
## Q2: How can a DDC cluster provide a higher level of security compared to a typical s...

### Answer

# How a DDC Cluster Provides Higher Security Compared to a Typical Stack from Databricks or Snowflake Running on AWS/Azure

## Direct Answer

DDC replaces traditional cloud infrastructure with a decentralized system featuring built-in on-chain verification, data distribution across multiple nodes via erasure coding, client-side encryption where even node operators cannot access plaintext content, and a trust model where operations are auditable and verifiable rather than assumed. Where traditional cloud stacks require you to trust the provider's infrastructure and logs, DDC shifts that to verifiable trust.

## Detailed Explanation

### Verifiable Trust vs. Provider Trust

The core security differentiation is stated explicitly: "Where traditional cloud stacks require you to trust the provider's infrastructure and logs, DDC shifts that trust that you can verify, rather than assume." [[chunk:p2-0022]] In a typical Databricks or Snowflake stack running on AWS/Azure, you rely on the provider's internal logging and infrastructure integrity. DDC instead provides built-in on-chain verification, meaning every operation is "auditable and verified on-chain." [[chunk:p2-0022]] This is enabled by the DAC (Data Activity Capture), described as a "Trust layer that captures real-time traffic and compute metrics, serving as the verified data source for blockchain-level inspection and automated payouts." [[chunk:p4-0023]]

### Data Distribution and Fragmentation

DDC uses erasure coding to distribute data across multiple nodes in the cluster. "Data is split into fragments, with each node storing only a portion of your files. For a malicious actor to reconstruction a file, they require control over a significant portion of the cluster." [[chunk:p2-0022]] [[chunk:p4-0023]] This is architecturally distinct from traditional cloud stacks where data typically resides within a single provider's infrastructure boundary. Small pieces use replication (multiple copies) while pieces larger than 16 KB use erasure coding. [[chunk:p2-0022]]

### Client-Side Encryption

"For sensitive data that requires protection at the storage level, client-side encryption is advised. By encrypting data before upload, you maintain complete control over your encryption keys, ensuring that only you can decrypt your data. Even node operators cannot access the plaintext content." [[chunk:p4-0023]] This means that unlike a centralized cloud provider that manages encryption keys (and could theoretically access data), DDC's model puts key control entirely in the client's hands.

### Access Control and Authentication

DDC provides "robust access control through bucket permissions (private/public) and owner-based authentication. This protects your data from unauthorized external access." [[chunk:p2-0022]] The SDK authenticates by "signing requests with a user key (derived from seed / wallet). Blockchain transactions are signed and sent to the chain endpoint; storage/compute requests to DDC nodes are signed by the same identity and verified by the node. Authorization is enforced based on bucket permissions (public/private) and on-chain customer/bucket state." [[chunk:p2-0042]]

### Protection Against Malicious Nodes

DDC has been designed with protections against malicious node operators. The system includes "Piece segment authentication (range requests) to protect receiving corrupted/incorrect data from potential malicious 3rd party nodes." [[chunk:p45-0074]] Additionally, Milestone 4 specifies that "Internal communication is protected against malicious activity. Each operation is authorized... Data transferred internally is authenticated by hashes." The acceptance criteria state: "Malicious node providers can't increase their income in a dishonest way (e.g. generate invalid activity report) or hurt the cluster (pollute the network, corrupt data etc.)." [[chunk:p32-0069]]

### Smart Contract Governance and SLA Adherence

The system achieves security "through advanced features like automated smart contract governance, real-time network monitoring, and strict SLA adherence." [[chunk:p4-0023]] The DDC Core's Resource Manager "enforces tenant quotas, and ensures strict SLA adherence" while the Storage Layer "maintains strict data sovereignty." [[chunk:p1-0054]]

### Secure AI Compute at the Edge

DDC enables "Secure Data Compute: Powered by sovereign AI frameworks (like Cef.ai), DDC enables private AI execution, ensuring that sensitive data and models remain secure at the edge." [[chunk:p2-0022]] This "moves compute to the data rather than data to the cloud," [[chunk:p2-0022]] reducing the exposure surface that exists when data must travel to centralized cloud processing facilities.

### Separation of Infrastructure and Protocol

"The tools and services offered by Cere ensure a clean separation of cloud infrastructure & operations from the protocol. This unique separation allows specialized data to reside on the edge, while also ensuring seamless integration and interoperability through the Cere L1 Blockchain and smart contracts." [[chunk:p4-0023]]

## Planned/Roadmap Items

- **SDK-integrated key management**: "Client-side encryption is available manually. SDK-integrated key management with delegated access grants is in development." [[chunk:p4-0023]]
- **Proof of storage audits**: "DDC audits stored data (some kind of proof of storage). The protocol ensures that data is stored over time. In case some data was lost or malicious nodes didn't store it at all, protocol should be able to detect it, report... and repair data in case it's needed." [[chunk:p32-0069]]
- **DAC malicious node detection**: "DAC is able to detect malicious nodes and remove them from the network." [[chunk:p47-0075]]
- **Compute usage metrics and cost tracking** (Milestone 3, August 2025): Compute nodes must generate logs and metrics detailing resources consumed. [[chunk:p2-0022]]

## What the Documents Do NOT Cover

- The documents do not describe specific security architectures of Databricks, Snowflake, AWS, or Azure for direct technical comparison.
- The documents do not discuss key loss scenarios — what happens if a user loses their client-side encryption keys.
- The documents do not describe specific encryption algorithms or cipher suites used.
- The documents do not detail how on-chain verification performs under adversarial conditions at scale.
- The documents do not provide compliance certifications (SOC 2, HIPAA, etc.) or comparisons with certifications held by traditional cloud providers.

## DOC_GAPS — Documentation Improvement Recommendations

1. **GAP**: No documentation on key loss/recovery for client-side encryption.
 - **IMPLICATION**: The docs state users "maintain complete control over your encryption keys" but don't address what happens if keys are lost.
 - **RECOMMENDATION**: Add a section in the Data Security documentation covering key recovery procedures, backup recommendations, and the consequences of key loss.

2. **GAP**: No specific comparison with named platforms (Databricks, Snowflake, AWS, Azure) on security features.
 - **IMPLICATION**: The docs contrast DDC with "traditional cloud stacks" generically but don't map specific features against competitors.
 - **RECOMMENDATION**: Create a security comparison matrix document that maps DDC security features against equivalent features in major cloud/data platforms.

3. **GAP**: No documentation on encryption standards, algorithms, or protocols used.
 - **IMPLICATION**: Client-side encryption is referenced but implementation details are absent.
 - **RECOMMENDATION**: Add a technical specification document detailing supported encryption algorithms, key derivation methods, and recommended configurations.

4. **GAP**: No documentation on compliance certifications or regulatory frameworks.
 - **IMPLICATION**: "Data sovereignty" and "secure data compute" are mentioned but regulatory compliance status is absent.
 - **RECOMMENDATION**: Add a compliance/regulatory document detailing which standards DDC meets or is pursuing.

5. **GAP**: The ADR on Encrypted Data Access and Key Delegation is referenced but not included in the evidence.
 - **IMPLICATION**: There may be additional security mechanisms documented elsewhere.
 - **RECOMMENDATION**: Ensure the ADR on Encrypted Data Access and Key Delegation is complete and publicly accessible.

## Citations Summary

- [[chunk:p2-0022]] — DDC overview, trust model comparison with traditional cloud, data durability, data security, edge-native AI
- [[chunk:p4-0023]] — Client-side encryption, DDC components, smart contract governance, separation of infrastructure
- [[chunk:p1-0054]] — DDC Core components including Resource Manager, Storage Layer, Compute Layer, DAC
- [[chunk:p2-0042]] — SDK authentication mechanism, request signing, authorization enforcement
- [[chunk:p45-0074]] — Milestone 2 security delivery sets, piece segment authentication, malicious node protections
- [[chunk:p47-0075]] — Phase 2/3 security testing, DAC malicious node detection
- [[chunk:p32-0069]] — Milestone 4 untrusted node protections, proof of storage, authentication gater, blockchain integration

### Scores

- **grounded_correctness:** 0.81
- **completeness:** 0.71
- **precision:** 0.70
- **clarity:** 0.86
- **citation_quality:** 0.72
- **Overall:** 0.76

---
## Q3: How can I store my data on this data cluster with my data wallet and key? What m...

### Answer

# How to Store Data on a DDC Cluster with Your Wallet and Key, and What Makes It Secure

## Direct Answer

To store data on a DDC cluster, you use the DDC Client SDK initialized with your wallet's mnemonic seed phrase, create a bucket on a cluster, and then upload data to that bucket. The data is secured through a combination of pallet-based (blockchain) access control, recursive JWT-like signed token chains for authorization, erasure coding for redundancy, and optional client-side encryption for data confidentiality.

## Detailed Explanation

### Storing Data with Your Wallet/Key

To store data, you first create a `DdcClient` instance using your wallet's mnemonic seed and connect to a DDC network (e.g., TESTNET). The account used must have a positive CERE token balance and a DDC deposit. You then create a bucket on a specific cluster and store files into that bucket. [[chunk:p6-0035]]

Here is the core workflow from the SDK documentation:

1. **Initialize the client** with your wallet seed: `const client = await DdcClient.create(user, TESTNET);` where `user` is your mnemonic seed phrase. [[chunk:p6-0035]]
2. **Ensure sufficient deposit**: Check your deposit with `client.getDeposit(clusterId)` and deposit CERE tokens if needed via `client.depositBalance(clusterId, 5n * CERE)`. [[chunk:p6-0035]]
3. **Create a bucket**: `const bucketId = await client.createBucket(clusterId, { isPublic: true });` — buckets can be public or private. [[chunk:p6-0035]]
4. **Store data**: Create a `File` instance from your data and call `const fileUri = await client.store(bucketId, ddcFile);` which returns a content identifier (CID). [[chunk:p6-0035]]

An alternative low-level approach uses the `StorageNode` API directly, where you create a `Piece` from content and call `storageNode.storePiece(bucketId, piece)` to get back a CID. [[chunk:p6-0043]]

For private buckets, you generate an access token: `const accessToken = await client.grantAccess(userSigner.address, { bucketId, operations: [AuthTokenOperation.GET], pieceCid: fileUri.cid });` [[chunk:p6-0035]]

### What Makes It Secure

**1. Pallet-Based (Blockchain) Access Control**

The bucket owner is defined during bucket creation, and the owner has root access stored in the pallet (on-chain smart contract). The pallet that holds bucket information can manage access control, so bucket owners can grant access at the pallet level. [[chunk:p5-0049]] DDC provides robust access control through bucket permissions (private/public) and owner-based authentication, protecting data from unauthorized external access. [[chunk:p4-0023]]

**2. Recursive Token-Based Authorization (Trust Chain)**

DDC uses recursive JWT-like signed tokens that represent a "trust chain" where the first token is issued by the client that has access on the pallet level and the last token is signed by the client sending a request to DDC. [[chunk:p7-0051]] Each link in the trust chain has a signature that secures the whole chain and it "can't be broken" — described as "similar as blockchain but in our case tokenchain." Trust chain roots are revocable on pallet level, meaning access can be revoked to all chains issued by that root in one operation. [[chunk:p13-0053]]

The token specification includes fields for: `subject` (whom access is granted to), `canDelegate` (whether further delegation is allowed), `bucketId`, `operations` (PUT, GET, DELETE), `expiresAt`, and `pieceCid`. Each next token in the trust chain must have less or equal privileges than the previous one, and must expire at the same time or earlier. [[chunk:p7-0051]]

**3. Data Distribution via Erasure Coding**

DDC uses erasure coding to distribute data across multiple nodes in the cluster, providing redundancy and availability. Data is split into fragments, with each node storing only a portion of files. For a malicious actor to reconstruct a file, they require control over a significant portion of the cluster. [[chunk:p4-0023]] Erasure coding targets enterprise-level durability guarantees comparable to AWS S3's 99.999999999% (11 nines), achievable with parameters like k=16 and n=40 with an expansion factor of 2.5. [[chunk:p3-0039]]

**4. Client-Side Encryption**

For sensitive data requiring protection at the storage level, client-side encryption is advised. By encrypting data before upload, you maintain complete control over your encryption keys, ensuring that only you can decrypt your data — even node operators cannot access the plaintext content. [[chunk:p4-0023]]

The target architecture encrypts data client-side with a DEK (Data Encryption Key), with the DEK shared via delegated encryption grants. In the current (unencrypted) flow, data is stored and transmitted in plaintext; in the target (encrypted) flow, only ciphertext passes through DDC nodes. [[chunk:p2-0001]]

The encryption system uses AES-256-GCM for data encryption, X25519 (ECDH) for key exchange, HKDF-SHA256 for key derivation, and Ed25519 for signing. [[chunk:p47-0018]] The user generates a DEK, encrypts data with AES-GCM, uploads the ciphertext to DDC, and creates an `EncryptionGrant` by wrapping the DEK via X25519 ECDH with the recipient's public key. [[chunk:p11-0007]]

**5. Encryption Grant Verification at Storage Nodes**

Storage nodes verify encryption grants by checking: delegation depth constraints, operations subset validity, TTL constraints, key references (via Key Escrow Service if used), and derivation proofs for derived keys. [[chunk:p41-0016]]

**6. Threat Mitigations**

The documented threat model addresses: compromised storage nodes (data encrypted client-side; nodes never see plaintext), key theft (keys never transmitted in plaintext; always wrapped via ECDH), replay attacks (timestamps and nonces in key fetch requests), privilege escalation (constraint validation at each delegation level), and agent key leakage (derived keys are short-lived and scoped). [[chunk:p47-0018]]

## Planned/Roadmap Items

As a planned capability, SDK-integrated key management with delegated access grants is in development. The current status is that client-side encryption is available manually. [[chunk:p4-0023]]

The implementation roadmap includes phases for: encryption grant in token (Phase 2), key derivation (Phase 3), Key Escrow Service (Phase 4), agent runtime integration (Phase 5), and an optional on-chain registry for encryption grants (Phase 6). [[chunk:p47-0018]]

## What the Documents Do NOT Cover

- The term "data wallet" is not used in the provided evidence. The documents reference mnemonic seed phrases and keypairs for authentication, but do not describe a specific "data wallet" product or interface.
- Key loss/recovery procedures are not addressed in the evidence.
- Specific steps for selecting or configuring a particular data cluster beyond providing a `clusterId` are not detailed in these chunks.

## DOC_GAPS — Documentation Improvement Recommendations

1. **GAP**: No documentation defines or describes a "data wallet" concept.
 - **IMPLICATION**: Users may expect a wallet-like interface for managing data access, but the docs only reference mnemonic seeds and keypairs.
 - **RECOMMENDATION**: Add a "Data Wallet" section to the Get Started guide explaining how wallet concepts (mnemonic, keypair, signer) map to DDC operations, or clarify that standard blockchain wallets serve this purpose.

2. **GAP**: Key loss scenarios are not documented.
 - **IMPLICATION**: If a user loses their mnemonic/private key, it is unclear whether data can be recovered.
 - **RECOMMENDATION**: Add a "Key Management and Recovery" section to the security documentation explaining the consequences of key loss and any recovery options.

3. **GAP**: The relationship between client-side encryption (currently manual) and the upcoming SDK-integrated encryption is not clearly bridged for end users.
 - **IMPLICATION**: Users may not understand how to encrypt data today vs. what will be available soon.
 - **RECOMMENDATION**: Add a transitional guide showing current manual encryption steps alongside the planned SDK approach.

4. **GAP**: Cluster selection criteria and how to identify which cluster to use are not covered.
 - **IMPLICATION**: Users asking "how to store on this data cluster" need guidance on cluster IDs and selection.
 - **RECOMMENDATION**: Add cluster discovery documentation to the Get Started guide.

## Citations Summary

- [[chunk:p6-0035]] — Get Started with DDC: client creation, bucket creation, file storage, access tokens
- [[chunk:p6-0043]] — DDC Client JS SDK Wiki: FileStorage API, low-level StorageNode API, CLI usage
- [[chunk:p5-0049]] — ADR Authentication and Authorization: pallet-based access control, token-based delegation
- [[chunk:p7-0051]] — ADR Authentication and Authorization: token specification, trust chain, SDK pseudocode
- [[chunk:p13-0053]] — ADR Authentication and Authorization: trust chain security properties, revocability
- [[chunk:p4-0023]] — DDC overview: access control, erasure coding, client-side encryption status
- [[chunk:p3-0039]] — Data Redundancy Strategy: erasure coding parameters, durability guarantees
- [[chunk:p2-0001]] — Encrypted Data Access and Key Delegation: current vs. target data flow, DEK concept
- [[chunk:p11-0007]] — Encrypted Data Access and Key Delegation: key hierarchy, encryption grant flow
- [[chunk:p41-0016]] — Encrypted Data Access and Key Delegation: storage node grant verification
- [[chunk:p47-0018]] — Encrypted Data Access and Key Delegation: implementation phases, threat model, cryptographic choices
- [[chunk:p11-0052]] — ADR Authentication and Authorization: token example, content sharing

### Scores

- **grounded_correctness:** 0.91
- **completeness:** 0.70
- **precision:** 0.70
- **clarity:** 0.85
- **citation_quality:** 0.75
- **Overall:** 0.81
