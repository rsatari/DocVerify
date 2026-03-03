# Encrypted Data Access and Key Delegation

<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: On-chain key registry was explicitly rejected due to latency and cost constraints incompatible with edge environments -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

In edge deployments, connectivity to key management infrastructure may be intermittent or unavailable. Applications requiring short-lived, self-contained access grants use embedded keys, while long-lived grants leverage external Key Escrow references where revocation is needed.

An on-chain key registry was evaluated and explicitly rejected for edge environments. The latency and cost constraints inherent to on-chain operations are incompatible with the responsiveness requirements of edge deployments, where round-trip confirmation times and per-transaction overhead cannot be absorbed into the access control path without degrading application performance.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The "data wallet" concept is defined repeatedly across multiple documents with slight variations, but no single canonica -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.quora.com/How-exactly-does-DataWallet-work] | [external: https://forum.solidproject.org/t/is-data-wallet-the-new-name-for-a-pod-or-something-else/9460] | [external: https://blog.zooxsmart.com/data-wallet-how-does-a-virtual-wallet-work] -->

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: A data wallet consists of a mnemonic seed phrase used to recover the keypair if access is lost -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] | [external: https://www.newsfilecorp.com/release/114279/DeFine-Partners-with-Cere-Network-to-Build-a-Decentralized-and-Secure-NFT-Ecosystem] -->

A data wallet is an sr25519 cryptographic keypair that serves as your identity within the DDC network. It consists of a public key, a private key, and a mnemonic seed phrase. The mnemonic seed phrase is a human-readable representation of the keypair and should be stored securely, as it is the only means of recovering access to your wallet if the original credentials are lost. Anyone who obtains the seed phrase can fully reconstruct the keypair and assume control of the associated wallet.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: A data wallet consists of a private key used to sign DDC operations -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] | [external: https://www.newsfilecorp.com/release/114279/DeFine-Partners-with-Cere-Network-to-Build-a-Decentralized-and-Secure-NFT-Ecosystem] -->

A data wallet is an sr25519 cryptographic keypair that serves as your identity within the DDC network. It consists of a public key, a private key, and a derived address. The private key is used to sign DDC operations, authorizing actions such as storing and retrieving data on the cluster. The public key and address identify your wallet to other participants in the network. To interact with DDC, you must initialize a client instance with a data wallet, which the SDK accepts as a keypair object.

<!-- EDIT-END: Q3 -->


A data wallet is the sr25519 keypair that represents an identity within the DDC network. It consists of three components: a public key, which functions as the on-chain address; a private key, used to sign DDC operations; and a mnemonic seed phrase, used to recover the keypair if access is lost. The terms "data wallet," "account," and "keypair" are interchangeable and refer to the same underlying cryptographic identity. This definition is normative across all DDC SDK documentation and supersedes any informal or context-specific variations found elsewhere.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: ** Key loss and seed phrase loss consequences are mentioned but no backup strategy guidance is provided. -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Key Backup Best Practices

Because DDC encrypts data client-side before submission to cluster nodes, the plaintext content and its Data Encryption Key (DEK) are never recoverable from the network itself. Loss of a DEK or its associated seed phrase results in permanent, irreversible inaccessibility of the encrypted data. Store all seed phrases and DEKs offline in at least two physically separate locations, such as printed paper copies in secure storage or hardware security devices kept off-network. No recovery path exists through DDC infrastructure, so redundant offline backups are the sole safeguard against permanent data loss.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The current state of DDC data storage is Plaintext -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://cere-network.medium.com/cere-launches-the-ddc-testnet-for-early-testing-63bddf8387c8] | [external: https://blog.polkastarter.com/get-to-know-cere-network/] -->

DDC currently stores data in plaintext by default. Node operators running DDC Core software have direct visibility into the data fragments stored on their individual nodes. Enterprise deployments requiring confidentiality must implement encryption within their own application layer before passing data to the DDC SDK. SDK-integrated encryption is under consideration for a future release but is not available in the current implementation. Developers building privacy-sensitive applications are responsible for encrypting data prior to submission.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Encryption is plaintext by default, yet several passages describe DDC as providing data confidentiality advantages over  -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] | [external: https://www.newsfilecorp.com/release/114279/DeFine-Partners-with-Cere-Network-to-Build-a-Decentralized-and-Secure-NFT-Ecosystem] -->

DDC does not encrypt data by default. Data passed to the DDC SDK is stored in plaintext unless the calling application encrypts it beforehand. Enterprise deployments requiring confidentiality must implement encryption at the application layer before submitting data to DDC. SDK-integrated encryption is not available in the current release and remains under consideration for a future version.

Where DDC offers a confidentiality advantage over centralized stacks, that advantage is architectural: key custody remains with the data owner rather than a third-party provider. This distinction applies only when application-layer encryption is already in place.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The DEK is not held by any administrative interface -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

The data encryption key (DEK) is generated and held exclusively by the client and is never transmitted to or stored by the DDC cluster. Clients are responsible for retaining the corresponding DEK through external key management mechanisms of their choosing. Because the cluster retains no copy of the DEK, it cannot decrypt stored content on behalf of any party, including Cere Network operators. No administrative override or cluster-level key recovery mechanism exists; loss of the DEK by the client results in permanent inaccessibility of the associated encrypted data.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The DEK is not held by any storage layer -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

The data encryption key (DEK) is generated and held exclusively by the client and is never transmitted to or stored by any layer of the DDC cluster. Because no cluster node retains a copy of the DEK, the cluster cannot decrypt stored content on behalf of any party, including Cere Network operators. Clients requiring shared or delegated access to encrypted data must manage DEK distribution through external key management mechanisms, coordinating access outside the cluster itself.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The DEK is not derivable from stored ciphertext -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

The data encryption key (DEK) is generated and held exclusively by the client and is never transmitted to or stored by the DDC cluster. Because the cluster retains no copy of the DEK, it cannot decrypt stored content on behalf of any party, including Cere Network operators. No administrative override or cluster-level key recovery mechanism exists. Clients who require access to encrypted data across sessions or devices must hold the corresponding DEK through external key management mechanisms, as the ciphertext stored within the cluster provides no pathway to derive or reconstruct the key.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The DEK is not included in upload requests -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

The data encryption key (DEK) is generated and managed exclusively by the client and is never included in upload requests transmitted to the DDC cluster. The cluster receives and stores only encrypted content, with no access to the keys required to decrypt it. Clients are responsible for retaining the corresponding DEK through external key management mechanisms. Because no copy of the DEK is held at the cluster level, neither DDC node operators nor Cere Network administrators can access or recover the plaintext content of stored data.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The DEK never crosses the client boundary -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

The data encryption key (DEK) is generated and held exclusively by the client and never transmitted to or stored by the DDC cluster. Clients who require access to encrypted content across sessions or devices must hold the corresponding DEK through external key management mechanisms. Because the cluster retains no copy of the DEK, it cannot decrypt stored content on behalf of any party, including Cere Network operators. No administrative override or cluster-level key recovery path exists; loss of the DEK by the client results in permanent inaccessibility of the associated encrypted data.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The accurate characterization is 'Client-side only; plaintext by default' -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

DDC clusters do not encrypt data at rest by default. Data stored within a cluster remains in plaintext unless the client application explicitly encrypts it prior to upload. This behavior is client-side only; no encryption is enforced at the node level.

Enterprise deployments requiring data confidentiality must implement encryption within their application layer before submitting data to DDC. Operators should not rely on the cluster itself to provide confidentiality guarantees. Any documentation or comparison material describing encryption at rest as default or node-enforced does not reflect current DDC behavior.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The SDK does not surface a descriptive error when DDC deposit is insufficient -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

Accounts that do not meet the minimum DDC deposit requirement will fail during client initialization. The SDK does not return a descriptive error in this case, making the failure difficult to diagnose. Ensure that the account holds a sufficient DDC deposit and satisfies all other initialization prerequisites before proceeding to client configuration. Verifying these conditions in advance prevents silent failures and reduces debugging overhead when integrating with DDC nodes through the SDK.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents state "SDK-integrated key management with delegated access grants is in development" but do not provide a  -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://landing.magic.link/hubfs/Marketing%20Collateral/Magic%20Whitepaper%20-%20DKMS%20Technical%20Overview%20Delegated%20Key%20Management%20System.pdf] | [external: https://docs.aws.amazon.com/kms/latest/developerguide/grants.html] | [external: https://www.cloudquery.io/blog/aws-kms-key-grants-deep-dive] -->

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents state encryption is "available manually" but do not provide a complete, standalone encryption tutorial wit -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.snowflake.com/en/fundamentals/data-encryption/] | [external: https://proton.me/learn/encryption] | [external: https://www.cryptomuseum.com/crypto/manual.htm] -->

By default, the DDC SDK transmits and stores data in plaintext. Encryption is not applied automatically at any layer of the SDK or cluster infrastructure. Enterprise deployments requiring data confidentiality must implement encryption within the application layer before passing data to the SDK.

The recommended approach is AES-256-GCM, a modern symmetric cipher that is computationally resistant to brute-force attacks under current conditions. Encrypt your payload locally, then upload the resulting ciphertext to DDC. Your application must manage key storage and retrieval independently, as the SDK provides no key management facilities in the current release.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: ** The documents state data is plaintext by default while also claiming DDC "removes the platform operator as a trusted  -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Data confidentiality in DDC is not automatic. By default, data is transmitted in plaintext between clients and storage nodes, and TLS is not enforced on client-to-node connections. The architectural claim that DDC removes the platform operator as a trusted intermediary in the confidentiality model is only realized when client-side encryption is explicitly implemented by the application developer. Production deployments must independently confirm that both TLS enforcement and SDK-level encryption are configured. Without these measures in place, DDC provides no confidentiality guarantees beyond those of a conventional centralized storage system.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Data is transmitted in plaintext in DDC -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://cere-network.medium.com/cere-launches-the-ddc-testnet-for-early-testing-63bddf8387c8] | [external: https://blog.polkastarter.com/get-to-know-cere-network/] -->

Data in DDC is transmitted and stored in plaintext by default. To protect sensitive content, DDC supports encrypted data access and key delegation, enabling applications to enforce access control at the data layer without relying solely on network-level permissions. Developers handling private or subscription-gated content should apply encryption before writing data to a bucket, ensuring that even if bucket access is misconfigured or a grace period exposes stored objects, the underlying data remains unreadable to unauthorized parties.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The DEK is generated and held exclusively by the client -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The Data Encryption Key (DEK) is generated exclusively on the client side and is never transmitted to or stored by the DDC cluster at any point during upload, storage, or retrieval operations. The cluster has no visibility into the DEK and does not participate in key management or content decryption. During data retrieval, the cluster validates access conditions against external systems, then returns encrypted content to the client, where decryption occurs locally using the client-held DEK. This architecture ensures that sensitive key material remains under the sole control of the data owner.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DDC currently has no encryption key delegation -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cere-network.medium.com/cere-launches-the-ddc-testnet-for-early-testing-63bddf8387c8] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-ddc-storage-node-improvements-update-8231a] -->

DDC does not currently implement encryption key delegation as a native protocol feature. Data stored within a DDC cluster can be encrypted by the client prior to upload, with the client retaining full custody of the associated encryption keys. Access control to encrypted data is therefore managed externally to the DDC protocol layer, and any key-sharing or delegation arrangements between parties must be handled through mechanisms outside of DDC itself. Applications requiring delegated decryption access should implement key management logic at the application layer.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q2 -->


SDK-integrated key management with delegated access grants is currently in active development. Target availability is planned for Q3. Upon release, this feature will enable applications to delegate encryption key access programmatically through the SDK, eliminating the need for manual key distribution workflows. Developers planning migration from manual encryption implementations should scope Q3 as the earliest viable transition window and design current integrations to remain compatible with delegated grant patterns, where permissions are issued, consumed, and retired within defined access lifecycles without requiring persistent credential management by the application layer.

<!-- EDIT-START: Q3 | track: flagged | 🟡 FLAGGED (spot-check recommended) -->
<!-- GAP: ** No step-by-step encryption guide exists in the Get Started flow. The Next Steps section lists "Set up content encrypt -->
<!-- SOURCES: [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Step 7: Encrypt Before Upload

DDC does not encrypt data by default. To protect sensitive content, generate a Data Encryption Key (DEK) on the client side and encrypt your data before passing it to client.store(). Using the @cere-ddc-sdk/ddc package, derive a DEK for each logical data group, apply symmetric encryption to the raw bytes, then store the ciphertext as the upload payload. The DEK itself should be managed and distributed separately through your access control layer. Only encrypted bytes should transit the network or reach DDC storage nodes.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q2 -->


*Source: Encrypted Data Access and Key Delegation.pdf | 56 pages | Extracted for DDC Documentation Evaluator*

---

<!-- PAGE 1 -->
## Page 1

[ADR] Encrypted Data Access
and Key Delegation
Status
Proposed by  Sergey Poluyan  Ulad Palinski
Stakeholders:  Fred Jin
Outcome
Status: planned
Executive Summary
This ADR extends the existing DDC authorization system to support encrypted
data storage with delegated key access for AI agents. It builds upon the recursive
token chain model documented in  ADR  Authentication and authorization , adding
encryption primitives that enable secure data sharing between users, data
services, and AI agents.
Key Goals:
Users can upload encrypted data to DDC
Encryption keys can be delegated to data services and AI agents
Access is verifiable and auditable
Keys can be added/revoked for existing data
Same authorization pattern applies to Storage and Compute layers
Context
Concept mapping
[ADR] Encrypted Data Access and Key Delegation 1

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The Get Started guide lists "Set up content encryption (client-side)" as a next step but provides no inline example or l -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://herothemes.com/blog/getting-started-guide/] | [external: https://document360.com/blog/write-a-getting-started-guide/] | [external: https://support.microsoft.com/en-us/office/introduction-to-lists-0a1c3ace-def0-44af-b225-cfa8d92c52d7] -->

Step 7: Encrypt Before Upload

DDC does not encrypt content automatically; protecting data before upload is the responsibility of the client application. Generate a Data Encryption Key (DEK), use it to encrypt your content locally, then upload the resulting ciphertext to DDC. The DEK itself can be managed through the same authorization pattern used across Storage and Compute layers, allowing access to be granted or revoked for existing data without re-uploading content. The following example demonstrates DEK generation, encryption, and upload of ciphertext using the DDC SDK:

const dek = crypto.getRandomValues(new Uint8Array(32));
const encrypted = await encryptContent(plaintext, dek);
await ddcClient.upload(encrypted, { resourceUri });

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The Get Started guide mentions "Set up content encryption (client-side)" as a next step but provides no inline example o -->
<!-- SOURCES: [internal: DDC from Sergey Poluyan.pdf (21 pages)] | [external: https://herothemes.com/blog/getting-started-guide/] | [external: https://document360.com/blog/write-a-getting-started-guide/] | [external: https://docs.nvidia.com/dgx/dgx-spark/first-boot.html] -->

Step 7: Encrypt Before Upload

DDC does not apply encryption to stored data by default. To protect sensitive content, generate a Data Encryption Key (DEK) on the client side before uploading. Use a standard symmetric cipher such as AES-256-GCM to encrypt the raw bytes locally, then upload the ciphertext to your chosen cluster. Store or escrow the DEK separately from DDC. To retrieve the content, download the ciphertext and decrypt it client-side using the same DEK. Without this step, data written to DDC buckets is stored and served in plaintext.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The DEK is held exclusively by the client -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The data encryption key (DEK) is generated and held exclusively by the client and is never transmitted to or stored by the DDC cluster. Because the cluster retains no copy of the DEK, it cannot decrypt stored content on behalf of any party, including Cere Network operators. No administrative override or cluster-level key recovery mechanism exists. This design ensures that data confidentiality is enforced architecturally rather than by policy, meaning access to plaintext content remains solely under the control of the client that performed the write operation.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DDC stores data in plaintext by default -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

DDC stores all uploaded data in plaintext by default. No automatic encryption is applied at the cluster or node level before or after upload. Users who require confidentiality must encrypt data client-side before submitting it to the cluster.

For use cases requiring controlled access to encrypted data, DDC supports an encrypted data access and key delegation model. Access is verifiable and auditable, and keys can be granted or revoked for existing data. This authorization pattern applies uniformly across both the Storage and Compute layers, supporting use cases such as AI agents and other programmatic consumers.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents do not provide a step-by-step guide for implementing client-side encryption as part of the standard onboar -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.cere.network/hub/how-video-encryption-decryption-works] | [external: https://github.com/Cerebellum-Network/cere-ddc-sdk-js/blob/main/packages/ddc-client/README.md] | [external: https://www.cere.network/hub/ddc] -->

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents do not describe what happens to the seed phrase during SDK initialization — specifically whether it is hel -->
<!-- SOURCES: [internal: DDC from Sergey Poluyan.pdf (21 pages)] | [external: https://strike.me/en/learn/what-is-a-seed-phrase/] | [external: https://www.blockchain.com/learning-portal/lessons/seed-phrases-explained] | [external: https://secuxtech.com/blogs/blog/what-is-a-seed-phrase?srsltid=AfmBOopoHreEgOOA10NEIOv-TXnUanx6PJCIbYjvj0qX5TxpvllTXt6F] -->

Seed Phrase Handling

When a seed phrase is provided to DdcClient.create(), the SDK derives the corresponding cryptographic key material from it. The seed phrase itself is not persisted to disk or transmitted externally. Security-conscious integrators should treat the seed phrase as sensitive in-process material for the duration of the initialization call and apply standard secure memory practices within their own runtime environment, such as avoiding logging the value and limiting its scope. Once key derivation is complete, retaining the seed phrase in application memory beyond that point is unnecessary and not recommended.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents do not provide a single, consolidated step-by-step guide that walks a user from wallet creation through en -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://sbk2.co/prepare-consolidated-financial-statements-example/] | [external: https://clickhelp.com/clickhelp-technical-writing-blog/how-to-write-a-step-by-step-guide/] | [external: https://www.anaplan.com/blog/preparing-consolidated-financial-statements-step-by-step-guide/] -->

Secure Storage Quick Start

To store encrypted data on DDC, complete the following steps in sequence. First, generate a wallet and fund it with a deposit to cover storage operations. Next, create a bucket to serve as the access-controlled container for your content. Before uploading, apply client-side encryption to your file. Finally, submit the encrypted file to your bucket via the SDK upload method.

Access control is enforced at the node level, meaning only authorized requests are processed by CDN and storage nodes. Read access can be scoped to an entire bucket, a single piece, or a defined collection of pieces.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents do not describe a concrete key backup or recovery procedure. -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.tencentcloud.com/techpedia/117356] | [external: https://rapidfilevault1.baby/backup-key-recovery-step-by-step-procedures-for-it-teams] | [external: https://cs.nyu.edu/~dodis/ps/cks.pdf] -->

Your DDC data wallet identity is secured by an sr25519 keypair. Loss of this key results in permanent, unrecoverable loss of access to all associated data. Before storing any data on DDC, record your wallet mnemonic phrase on paper and store copies in at least two physically separate locations. For higher-assurance environments, generate and store the key within a hardware security module or secure key vault, and encrypt any exported key material with a strong passphrase as an additional protection layer. Never store your mnemonic phrase solely in digital form on an internet-connected device.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The data wallet output includes an address -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] -->

When initializing a data wallet within the DDC SDK, the output includes a wallet address that serves as the identity anchor for data access and ownership operations. This address is used by DDC's authentication mechanism to associate stored data with a specific owner, enabling access control scenarios such as NFT-gated content. For example, a verified NFT ownership state can be mapped to a wallet address, allowing DDC to grant or revoke data access automatically without requiring direct client involvement in the authorization process.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents do not describe a complete end-to-end flow for client-side encryption using the current SDK (without the p -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/hub] | [external: https://cs.nyu.edu/~dodis/ps/cks.pdf] -->

Before uploading sensitive content, encrypt it client-side using AES-256-GCM prior to calling any DDC storage method. The following pattern is supported with the current SDK: generate a random 256-bit key and IV, encrypt the raw bytes using the Web Crypto API or a compatible Node.js equivalent, then pass the resulting ciphertext buffer to the DDC client upload method. On retrieval, download the ciphertext and decrypt locally using the same key and IV. The DDC client identity uses sr25519 keys; the encryption key is a separate secret managed entirely by the application and never transmitted to the cluster.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents do not specify what happens to data confidentiality if client-side encryption fails or is improperly imple -->
<!-- SOURCES: [internal: DDC from Sergey Poluyan.pdf (21 pages)] | [external: https://www.cere.network/blog/cere-network-s-crucial-head-start-on-complying-with-data-protection-regulations-2e5f9] | [external: https://github.com/Cerebellum-Network/cere-ddc-sdk-js/blob/main/packages/ddc-client/README.md] | [external: https://www.cere.network/hub/how-video-encryption-decryption-works] -->

DDC's data confidentiality guarantee is entirely dependent on correct client-side implementation. The protocol does not validate or reject unencrypted payloads at ingestion time, meaning that if an application fails to encrypt data before writing to DDC, those records are stored as plaintext across cluster nodes with no automatic remediation. There is no protocol-level enforcement to detect or prevent this condition. Operators and integrators must treat encryption as a mandatory application-layer responsibility and establish independent verification procedures to confirm that all payloads are encrypted prior to submission.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q3 | track: flagged | 🟡 FLAGGED (spot-check recommended) -->
<!-- GAP: ** The documents do not describe what happens to stored data if the user loses their seed phrase or encryption key. -->
<!-- SOURCES: [external: https://republic.com/cere] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://cere-network.medium.com/cere-launches-the-ddc-testnet-for-early-testing-63bddf8387c8] -->

Warning: Permanent Data Loss from Lost Credentials

Access to encrypted data stored in DDC is permanently and irrecoverably lost if the associated seed phrase or Data Encryption Key (DEK) is lost. DDC's decentralized architecture means there is no account recovery mechanism, password reset process, or administrative override available. Users and integrators are solely responsible for securely backing up seed phrases and DEKs using offline or redundant storage methods before writing data to any DDC cluster. Treat these credentials with the same criticality as private keys controlling on-chain assets.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: There is no encryption key delegation currently -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://republic.com/cere] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://www.cere.network/blog/cere-partnerships-overview-c1862] -->

Encryption key delegation in DDC is not currently supported. Access control to encrypted data is managed at the node level, where a client's permissions are determined by their relationship to a given entry point in the data graph. Using the DAG API, data can be structured hierarchically and accessed by path, enabling parent-child node relationships similar to shared folder access. Authorized clients can traverse this structure based on their access to a parent node, but cryptographic key delegation to third parties remains outside the scope of the current implementation.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The documents do not provide a unified, step-by-step guide for encrypting data before upload as part of the standard get -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.hexnode.com/blogs/data-encryption-a-beginners-guide/] | [external: https://www.splunk.com/en_us/blog/learn/data-encryption-methods-types.html] | [external: https://www.snowflake.com/en/fundamentals/data-encryption/] -->

By default, data uploaded to a DDC bucket is stored as plaintext. Any client with read access to the bucket can retrieve the raw content. To protect sensitive data, encrypt it locally before passing it to the upload method using a Data Encryption Key (DEK). Generate a DEK, encrypt your payload with it, then upload the ciphertext. Access control alone does not substitute for encryption, as authorization governs who may request content but does not obscure the content itself from nodes handling the data in transit or at rest.

<!-- EDIT-END: Q3 -->


By default, DDC stores data as plaintext. To achieve encryption at rest, generate a Data Encryption Key (DEK) on the client before upload, encrypt the content locally using the DEK, and store only the ciphertext in DDC. For per-asset isolation, derive a unique DEK per piece using a nonce and the root DEK via deriveDek(nonce, videoDek) before encrypting with naclDecrypt or its encryption counterpart. Back up the DEK securely outside DDC; loss of the DEK renders encrypted content permanently inaccessible. Server-side encryption is available as a fallback when client-side processing is not possible.

<!-- EDIT-END: Q2 -->


---

<!-- PAGE 2 -->
## Page 2

Concept AWS Equivalent DDC Concept
Identity IAM User / Role Wallet Address  Ed25519 
Authorization IAM Policy AuthToken  Signed JWT-like)
DEK  AES 256) wrapped in an
Encryption Key KMS Key
EncryptionGrant
KES  Key Escrow Service) or
Key Manager AWS KMS Service
Embedded
DDC Infrastructure Layers
The DDC system consists of two primary layers:
Layer Description Distribution Model
Decentralized content-addressed Fully decentralized (blockchain-
Storage
storage verified)
Distributed (orchestrator-
Compute AI agent execution runtime
managed)
Current Data Flow (Unencrypted)
flowchart LR
subgraph Current["Current: Plaintext"]
User1[User] -->|plaintext| Node[DDC Node]
Node <-->|plaintext| Agent1[Agent]
end
User1 -.->|AuthToken| Node
Node -.->|Token Verification| Node
style User1 fill:#ffcccc
style Node fill:#ffcccc
style Agent1 fill:#ffcccc
Problem: Data is stored and transmitted in plaintext. Storage nodes and network
intermediaries can read user data.
[ADR] Encrypted Data Access and Key Delegation 2

<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Data is stored and transmitted in plaintext in DDC -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://blog.polkastarter.com/get-to-know-cere-network/] | [external: https://cere-network.medium.com/cere-launches-the-ddc-testnet-for-early-testing-63bddf8387c8] -->

DDC does not currently enforce TLS on client-to-node connections by default. Data is transmitted in plaintext between clients and storage nodes, and production deployments should confirm that TLS is enforced independently of any SDK-level encryption controls. Operators running storage nodes or CDN nodes within a cluster are responsible for validating that transport layer security is applied at the infrastructure level. Applications handling sensitive data should not rely solely on DDC defaults and must independently verify that encrypted transport is configured before moving workloads to production.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Blockchain transactions are signed and sent to the chain endpoint -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/hub/blockchain-protocol] | [external: https://republic.com/cere] -->

The SDK authenticates all operations by signing requests with a user key derived from a seed or wallet. Blockchain transactions are signed and sent to the chain endpoint, while storage and compute requests to DDC nodes are signed by the same identity and verified at the node level. This unified signing model ensures that a single user identity governs both on-chain and off-chain interactions, eliminating the need for separate credential management across the decentralized infrastructure.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: After bucket creation, the wallet that created bucket becomes a bucket owner that has root access -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://docs.datahaven.xyz/store-and-retrieve-data/use-storagehub-sdk/create-a-bucket/] | [external: https://docs.aws.amazon.com/AmazonS3/latest/userguide/create-bucket-overview.html] | [external: https://medium.com/@csjcode/how-hackers-stole-1-5-billion-crypto-in-an-aws-s3-bucket-exploit-f0a0ce39ccd0] -->

When a bucket is successfully created on DDC, the submitting wallet address is automatically assigned as the bucket owner. The bucket owner holds root access to that bucket, meaning they retain full administrative control over its contents and access policies. This ownership is derived deterministically from the wallet address used to sign the creation transaction. Protecting the private key associated with the owner wallet is therefore critical, as compromise of that key constitutes full compromise of the bucket and any data stored within it.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The bucket owner is automatically granted root access to that bucket -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://republic.com/cere] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://www.cere.network/blog/cere-partnerships-overview-c1862] -->

When a bucket is created in DDC, the owner is automatically granted root access to that bucket. This root access allows the owner to perform all operations on the bucket, including read, write, and delete, as well as delegate access permissions to other parties. The owner can grant scoped access to additional users, restricting or extending their permissions as needed. For example, a bucket owner may share access with multiple users, enabling each to upload or download data while the owner retains ultimate control over the bucket's access policies.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: After bucket creation, the wallet that created the bucket becomes the bucket owner with root access -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://docs.datahaven.xyz/store-and-retrieve-data/use-storagehub-sdk/create-a-bucket/] | [external: https://docs.aws.amazon.com/AmazonS3/latest/userguide/create-bucket-overview.html] | [external: https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/minimum-viable-data-space-share-data-organizations.html] -->

When a bucket is created in DDC, the wallet address that initiated the transaction automatically becomes the bucket owner. Bucket ownership confers root access, representing the highest level of permission within that bucket's access control hierarchy. This ownership model is enforced at the pallet level, providing a foundational layer of access governance. From this privileged position, the bucket owner can subsequently grant access to other parties, enabling delegated permission structures while retaining ultimate control over the bucket and its contents.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DAC is the trust layer that captures real-time traffic and compute metrics, serving as the verified data source for bloc -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/hub/blockchain-protocol] | [external: https://republic.com/cere] -->

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DAC is the Trust layer that captures real-time traffic and compute metrics, serving as the verified data source for bloc -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/hub/blockchain-protocol] | [external: https://republic.com/cere] -->

The Data Activity Capture (DAC) layer functions as the trust foundation within DDC, monitoring real-time traffic and compute metrics across clusters. These verified measurements are recorded as validation results on the Cere Blockchain, which serves as an immutable repository ensuring transparency in data operations. By anchoring activity metrics to on-chain validation, DAC enables automated, auditable payouts without reliance on a single service provider. This architecture ensures that all billing and access decisions are grounded in cryptographically verifiable data rather than centralized reporting, preserving the integrity of the broader DDC trust model.

<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: All access decisions in DDC are grounded in cryptographically verifiable data -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://cere-network.medium.com/cere-launches-the-ddc-testnet-for-early-testing-63bddf8387c8] | [external: https://blog.polkastarter.com/get-to-know-cere-network/] -->

All access decisions in DDC are grounded in cryptographically verifiable data rather than centralized reporting. By anchoring activity metrics to on-chain validation, the Data Availability Committee (DAC) enables automated, auditable evaluation of both billing and access requests without reliance on a single service provider. This architecture preserves the integrity of the broader DDC trust model, ensuring that no unilateral or opaque authority can govern data operations. The result is a transparent, tamper-resistant foundation in which access control outcomes can be independently verified by any participant in the network.

<!-- EDIT-END: Q2 -->


<!-- EDIT-END: Q3 -->


The Data Activity Capture (DAC) layer functions as the trust foundation within DDC, monitoring real-time traffic and compute metrics across clusters. These captured metrics serve as the verified data source for blockchain-level inspection, enabling the Cere Blockchain to store validation results as an immutable record. This architecture ensures that automated payouts and access decisions are grounded in cryptographically verifiable activity rather than self-reported data. Each interaction is anchored to a data wallet keypair, which underpins the trust model governing all data operations across DDC clusters.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The wallet that created bucket becomes a bucket owner that have the root access -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://conelibags.com/products/the-bucket-wallet?srsltid=AfmBOooMRfdiXzXm82XPYv83w60XWJU2RJOueTx-O7poDoqWfj-wybc-] | [external: https://www.investopedia.com/terms/b/bucket.asp] | [external: https://www.betterinvesting.org/learn-about-investing/investor-education/personal-finance/the-bucket-approach] -->

When a bucket is created on DDC, the wallet that initiated the creation is designated as the bucket owner and is automatically granted root access to that bucket. This ownership model is enforced at the pallet level, providing high-level access control as a foundational layer of the DDC authentication and authorization architecture. Following creation, the bucket owner may grant access to other clients, enabling delegated permissions without transferring ownership. This combined approach integrates pallet-based access control with token-based access delegation to support flexible, multi-party data access scenarios.

<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DDC authentication gater can authenticate clients even when the blockchain is unavailable and customer information isn't -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/hub/blockchain-protocol] | [external: https://cere-network.medium.com/building-distributed-systems-with-blockchain-technology-277c402eff94] -->

The DDC authentication gateway relies on bucket ownership and access control records anchored at the blockchain pallet level. Because this ownership model is enforced on-chain, the gateway depends on the Cere Blockchain as its authoritative source for client permissions. When the blockchain is unavailable and no cached records exist for a given client, the gateway cannot independently verify ownership or delegated access rights, and authentication requests for that client will not succeed until connectivity is restored or a valid cache entry becomes available.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Pallet-based access is revocable -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://www.pallet.com/blog/security-overview] | [external: https://www.oligo.security/blog/what-is-adr-application-detection-and-response] | [external: https://arcb.com/sites/default/files/pdf/ARC111-2022-11-07.pdf] -->

Bucket access permissions granted through the pallet-based access control layer are revocable by the bucket owner at any time. Following initial bucket creation, the owner may grant delegated permissions to other clients without transferring ownership, and may subsequently revoke those permissions as access requirements change. This revocability is a deliberate property of the foundational authentication and authorization architecture, ensuring that multi-party data access scenarios remain under the continuous control of the originating owner. Token-based access delegation operates alongside pallet-based controls to support flexible permission management across the full access lifecycle.

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Data is stored in plaintext by default in DDC -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The authentication gater was migrated to use bucket and customer indexes persisted on disk -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The authentication gater maintains bucket and customer indexes that are persisted on disk, enabling efficient lookup and validation of access rights without requiring repeated on-chain queries. These indexes are loaded at node startup and updated as new buckets are created or customer permissions change, ensuring the gater operates with current state while minimizing latency during request handling.

By storing these indexes locally, DDC nodes can authenticate incoming requests against bucket ownership and customer entitlements in a performant manner. This approach supports the broader DDC security model, where smart contracts define permissions and node-level components enforce them at the data access layer.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The authentication gater uses bucket and customer indexes persisted on disk -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The authentication gater maintains bucket and customer indexes that are persisted to disk, enabling efficient access control decisions without requiring repeated on-chain lookups. These indexes are loaded at node startup and updated as the underlying smart contract state changes, allowing the gater to validate incoming requests against current bucket ownership and customer permissions with low latency.

By storing this index data locally, DDC nodes can enforce access policies at the edge of the cluster while remaining synchronized with the authoritative state recorded on-chain. This design supports the trustless data transfer model central to DDC, where security guarantees are preserved without sacrificing throughput.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The authentication gater is using bucket and customer indexes persisted on disk -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The authentication gater verifies customer balance and debt before granting access to DDC resources. To support this, customer and bucket indexes are persisted on disk, enabling the gater to perform access control checks without querying the blockchain on every request. These indexes are maintained as local replicas of on-chain state, reflecting the smart contract-managed relationships between customers, buckets, and storage nodes that underpin the DDC architecture. Keeping this data on disk ensures low-latency authentication decisions while preserving consistency with the decentralized trust model governing the cluster.

<!-- EDIT-END: Q2 -->


By default, data stored in DDC is retained in plaintext unless encryption is applied at the application layer prior to upload. Developers integrating DDC should account for this when handling sensitive user data, as the storage layer itself does not enforce confidentiality. Access control at the bucket level can restrict retrieval, but this is distinct from encryption-at-rest. Applications requiring confidentiality are responsible for encrypting data client-side before writing to DDC, ensuring that stored content remains protected independent of bucket permission state.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: ** No explicit end-to-end tutorial for encrypting data before upload using the current SDK. -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://cere-network.medium.com/ceres-decentralized-data-cloud-to-be-used-by-credefi-in-collaboration-with-big-three-global-credit-39d38f49d3c6] | [external: https://republic.com/cere] -->

Step 7: Encrypt Before Upload

DDC storage does not enforce confidentiality at the infrastructure level, so applications handling sensitive data must encrypt content client-side before calling client.store(). Generate a 256-bit data encryption key using crypto.getRandomValues, then encrypt the payload with AES-256-GCM before passing the resulting ciphertext as the upload body. The following pattern applies regardless of bucket permission configuration, ensuring stored content remains protected independent of access control state.

const dek = crypto.getRandomValues(new Uint8Array(32));
const iv = crypto.getRandomValues(new Uint8Array(12));
const key = await crypto.subtle.importKey("raw", dek, "AES-GCM", false, ["encrypt"]);
const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
await client.store(bucketId, new Uint8Array(ciphertext));

<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The term "data wallet" is never formally defined in any document despite being used as a key concept. -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/blog/decentralized-data-governance-for-enterprises-2e755] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://republic.com/cere] -->

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The term "data wallet" is used frequently but has no single canonical definition in the source documents. -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.chainscorelabs.com/en/glossary/web3-social-and-creator-economy-models/decentralized-social-networking-protocols/data-wallet] | [external: https://blog.zooxsmart.com/data-wallet-how-does-a-virtual-wallet-work] | [external: https://www.natwest.com/corporates/sibos-2024/data-wallets-article.html] -->

A data wallet is the sr25519 keypair generated by running `npx @cere-ddc-sdk/cli account --random`. It consists of three components: a public key, which serves as your on-chain address; a private key, used to sign DDC operations; and a mnemonic seed phrase, used to recover the keypair. The terms "data wallet" and "account" refer to the same underlying keypair. Store the seed phrase securely and never share it, as anyone with access to it can fully reconstruct your private key and assume control of your DDC account.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The term "data wallet" is never formally defined in any specification document. -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://forum.solidproject.org/t/is-data-wallet-the-new-name-for-a-pod-or-something-else/9460] | [external: https://blog.zooxsmart.com/data-wallet-how-does-a-virtual-wallet-work] | [external: https://mydata.org/2023/12/15/wallets-data-safes-and-key-safes-formidable-competitors-or-good-partners/] -->

A data wallet is an sr25519 keypair generated via the DDC CLI that serves as your cryptographic identity within DDC. It is distinct from a blockchain account or token wallet: rather than holding funds, it establishes ownership and access rights over data stored in a DDC cluster. All read and write operations are signed with this keypair, allowing the network to verify the requester's identity without a centralized authority. You create a data wallet once and reference it across subsequent CLI commands and SDK calls throughout your session.

<!-- EDIT-END: Q3 -->


A data wallet is an sr25519 keypair that serves as your cryptographic identity within DDC. It is distinct from the Cere Wallet UI or any other wallet software you may use to manage on-chain assets. The keypair is used to sign requests, authenticate access to data clusters, and establish ownership of stored content within the DDC protocol. When documentation refers to creating or importing a data wallet, it refers specifically to generating or providing this keypair, not to any browser extension or custodial interface.

<!-- EDIT-END: Q3 -->


---

<!-- PAGE 3 -->
## Page 3

Target Data Flow (Encrypted)
flowchart LR
subgraph Target["Target: Encrypted"]
User2[User] -->|ciphertext| Node[DDC Node]
Node <-->|ciphertext| Agent2[Agent]
end
User2 -.->|AuthToken + EncryptionGrant| Node
Node -.->|Token + Grant Verification| Node
Agent2 -.->|DEK via Grant / Decrypt in V8| Node
style User2 fill:#ccffcc
style Node fill:#ccffcc
style Agent2 fill:#ccffcc
Solution: Data encrypted client-side with DEK  Data Encryption Key). DEK shared
via delegated encryption grants.
Current Authorization System
Recursive Token Chain
The DDC uses a recursive JWT-like token chain where each token delegates a
subset of permissions to the next:
flowchart TB
subgraph TokenChain["Token Chain Structure"]
Root["🔐 ROOT TOKEN<br/>(Bucket Owner)<br/>subject: 0
xabc"]
Delegated["📜 DELEGATED TOKEN<br/>(Agent Service)<br/
>subject: 0xdef"]
Final["✅ FINAL TOKEN<br/>(Agent)<br/>subject: empt
y"]
Root -->|prev| Delegated
[ADR] Encrypted Data Access and Key Delegation 3

---

<!-- PAGE 4 -->
## Page 4

Delegated -->|prev| Final
end
Root -.- Note1["Signed by bucket owner<br/>(on-chain veri
fied)"]
Root -.- Note2["Grants access to Agent Service"]
Delegated -.- Note3["Signed by Agent Service (0xabc)"]
Delegated -.- Note4["Grants access to specific agent"]
Final -.- Note5["Signed by Agent (0xdef)"]
Final -.- Note6["Terminal token<br/>(no further delegatio
n)"]
style Root fill:#e1f5fe
style Delegated fill:#fff3e0
style Final fill:#e8f5e9
Current Token Specification
message Signature {
Algorithm algorithm = 1; // ED_25519 or SR_25519
bytes signer = 2; // Public key of signer
bytes value = 3; // Signature bytes
}
message AuthToken {
Signature signature = 1;
Payload payload = 2;
}
message Payload {
optional AuthToken prev = 1; // Previous token in chai
n
optional bytes subject = 2; // Recipient public key
optional bool canDelegate = 3; // Can subject further de
legate?
[ADR] Encrypted Data Access and Key Delegation 4

---

<!-- PAGE 5 -->
## Page 5

optional uint64 bucketId = 4; // Target bucket
repeated Operation operations = 5; // Allowed operations
optional int64 expiresAt = 6; // Expiration timestamp
optional bytes pieceCid = 7; // Specific piece access
}
enum Operation {
UNKNOWN = 0;
PUT = 1;
GET = 2;
DELETE = 3;
}
Token Verification Flow
// Simplified verification in storage node
func (g *gater) expandAndVerifyToken(token *AuthToken, expand
ed *ExpandedToken, depth int) error {
// 1. Verify signature
if !verifySignature(token) {
return ErrInvalidSignature
}
// 2. Check expiration
if token.IsExpired() {
return ErrExpired
}
// 3. Validate expiration chain (child <= parent)
if expanded.expiresAt != 0 && expanded.expiresAt > token.
Payload.ExpiresAt {
return ErrInvalidExpirationTime
}
// 4. Validate permissions (child ⊆ parent)
[ADR] Encrypted Data Access and Key Delegation 5

---

<!-- PAGE 6 -->
## Page 6

if !permissionsValid(expanded.operations, token.Payload.O
perations) {
return ErrInvalidPermissions
}
// 5. Validate issuer matches previous subject
if len(expanded.rootIssuer) > 0 && !bytes.Equal(expanded.
rootIssuer, token.Payload.Subject) {
return ErrInvalidIssuer
}
// 6. Recurse to parent token
if token.Payload.Prev != nil {
return g.expandAndVerifyToken(token.Payload.Prev, exp
anded, depth+1)
}
// 7. Root token: verify bucket ownership on-chain
return g.verifyBucketOwnership(token.Signature.Signer, ex
panded.bucketID)
}
Current Limitations
Aspect Current State Limitation
Data Privacy Plaintext storage Storage nodes can read data
Key Management None No encryption key delegation
Agent Access Token-based No secure key delivery to agents
Problem Statement
Primary Use Case: Secure AI Agent Data Access
[ADR] Encrypted Data Access and Key Delegation 6

---

<!-- PAGE 7 -->
## Page 7

flowchart TB
subgraph UseCase["🎯 Use Case: Secure AI Agent Data Acces
s"]
Step1["󾠮 User 0x123 has sensitive data"]
Step2["󾠯 User delegates write access to Agent Servic
e 0xabc"]
Step3["󾠰 Agent Service deploys AI agents that need t
o process user data"]
Step4["󾠱 Agents should only access data with user's
permission"]
Step5["󾠲 Keys must expire and be revocable"]
Step1 --> Step2 --> Step3 --> Step4 --> Step5
end
style Step1 fill:#e3f2fd
style Step2 fill:#fff3e0
style Step3 fill:#f3e5f5
style Step4 fill:#e8f5e9
style Step5 fill:#ffcdd2
Challenges
   Client-Side Encryption: Users must encrypt data before upload
   Key Delegation: DEK must be securely shared with authorized parties
   Hierarchical Access: User → Data Service → Agent hierarchy
   Revocability: Must be able to revoke access to existing encrypted data
   Verification: Storage and compute nodes must verify encryption grants
   Uniformity: Same pattern for storage API and compute context API
Requirements
[ADR] Encrypted Data Access and Key Delegation 7

---

<!-- PAGE 8 -->
## Page 8

Functional Requirements
Requirement Priority
Users can upload encrypted data to DDC Must Have
Users can grant encryption key access to data services Must Have
Data services can derive time-limited keys for agents Must Have
Users can add grants to existing encrypted data Must Have
Users can revoke grants for existing encrypted data Must Have
Agents access encrypted data via context API Must Have
Storage nodes verify encryption grants Should Have
All key access is auditable Should Have
Keys auto-expire based on grant constraints Must Have
Same pattern works for storage and compute Must Have
Non-Functional Requirements
Requirement Metric
Key derivation latency < 10ms
Grant verification latency < 5ms
Revocation propagation < 1 minute
Encryption overhead < 5% of data size
No single point of failure for key access 99.9% availability
Design Decisions
1. Extend AuthToken (vs. Separate System)
Decision: Extend the existing with encryption grant fields.
AuthToken
Rationale:
Maintains single authorization primitive
Leverages existing token verification infrastructure
Backward compatible (encryption grant is optional)
[ADR] Encrypted Data Access and Key Delegation 8

---

<!-- PAGE 9 -->
## Page 9

Consistent developer experience
Alternatives Considered:
Separate : Rejected due to complexity of managing two token
EncryptionToken
types
On-chain encryption registry: Rejected due to latency and cost
2. Hybrid Key Management
Decision: Support both embedded DEK (in token) and key reference (via Key
Escrow Service).
Rationale:
Embedded DEK  Simple, offline, suitable for short-lived grants
Key reference: Enables revocation, suitable for long-lived grants
Applications choose based on their requirements
3. HKDF for Key Derivation
Decision: Use HKDF SHA256 for deriving agent keys from service keys.
Rationale:
Industry standard  RFC 5869 
Deterministic: Same input produces same output
Supports context binding (agent ID, nonce)
Compatible with WebCrypto API (runs in V8 
4. AES-256-GCM for Data Encryption
Decision: Use AES 256 GCM for symmetric encryption.
Rationale:
Authenticated encryption (confidentiality + integrity)
Hardware acceleration available
WebCrypto API support
[ADR] Encrypted Data Access and Key Delegation 9

---

<!-- PAGE 10 -->
## Page 10

Industry standard for data at rest
5. X25519 for Key Exchange
Decision: Use X25519  Curve25519 ECDH) for encrypting DEK to recipients.
Rationale:
Compatible with Ed25519 keys (can derive X25519 from Ed25519 
Fast and secure
Widely supported
Architecture
System Overview
flowchart TB
subgraph User["👤 USER (0x123)"]
direction LR
Ed25519["🔑 Ed25519 Key<br/>(Signing)"]
X25519["🔐 X25519 Key<br/>(Encryption)"]
KeyMgr["📋 Key Manager<br/>• Generate DEK<br/>• Encry
pt data with DEK<br/>• Create EncryptionGrants<br/>• Manage g
rant lifecycle"]
end
subgraph AgentService["🏢 AGENT SERVICE (0xabc)"]
subgraph KDS["Key Derivation Service"]
direction LR
Grant["User's Grant"] --> DecryptDEK["Decrypt DE
K"]
DecryptDEK --> DeriveKeys["Derive Agent Keys"]
DeriveKeys --> Wrap["Wrap"]
DecryptDEK --> ServiceDEK["Service DEK"]
DeriveKeys --> AgentDEKs["Agent-specific DEKs"]
end
[ADR] Encrypted Data Access and Key Delegation 10

---

<!-- PAGE 11 -->
## Page 11

end
subgraph Agents["🤖 AI AGENTS (V8 Isolates)"]
direction LR
Alpha["Agent Alpha<br/>HKDF(svc, alpha)<br/>context.e
ncryption.decrypt(...)"]
Beta["Agent Beta<br/>HKDF(svc, beta)<br/>context.encr
yption.decrypt(...)"]
Gamma["Agent Gamma<br/>HKDF(svc, gamma)<br/>context.e
ncryption.decrypt(...)"]
end
User -->|"AuthToken + EncryptionGrant"| AgentService
AgentService -->|"Derived Tokens + Wrapped DEKs"| Agents
style User fill:#e3f2fd
style AgentService fill:#fff8e1
style Agents fill:#e8f5e9
style Alpha fill:#c8e6c9
style Beta fill:#c8e6c9
style Gamma fill:#c8e6c9
Key Hierarchy
flowchart TB
MasterKey["🔑 User Master Key<br/>(Ed25519 Keypair)"]
DEK["🔐 Data Encryption Key<br/>(AES-256, per-piece)"]
MasterKey -->|Generates| DEK
DEK -->|"ECDH Wrap (X25519)"| WrappedA["📦 Wrapped DEK fo
r<br/>Agent Service A (0xabc)"]
DEK -->|"ECDH Wrap (X25519)"| WrappedB["📦 Wrapped DEK fo
r<br/>Agent Service B (0xdef)"]
[ADR] Encrypted Data Access and Key Delegation 11

---

<!-- PAGE 12 -->
## Page 12

WrappedA -->|HKDF Derivation| Agent1["🤖 Agent 1 Key"]
WrappedA -->|HKDF Derivation| Agent2["🤖 Agent 2 Key"]
WrappedA -->|HKDF Derivation| Agent3["🤖 Agent 3 Key"]
style MasterKey fill:#e1f5fe
style DEK fill:#fff3e0
style WrappedA fill:#f3e5f5
style WrappedB fill:#f3e5f5
style Agent1 fill:#e8f5e9
style Agent2 fill:#e8f5e9
style Agent3 fill:#e8f5e9
Encryption Grant Flow
sequenceDiagram
autonumber
participant User as 👤 User (0x123)
participant DDC as 💾 DDC Node
participant Service as 🏢 Agent Service (0xabc)
participant Agent as 🤖 AI Agent
rect rgb(227, 242, 253)
Note over User: 1. USER CREATES ENCRYPTED DATA
User->>User: Generate DEK (AES-256)<br/>dek = crypto.
randomBytes(32)
User->>User: Encrypt Data<br/>ciphertext = AES-GCM(pl
aintext, dek, nonce)
User->>DDC: Upload ciphertext<br/>cid = ddc.store(buc
ketId, ciphertext)
User->>User: Create EncryptionGrant<br/>ephemeralKey
= X25519.generate()<br/>sharedSecret = X25519.ecdh(ephemeralK
ey, servicePubKey)<br/>wrappedDEK = AES-GCM(dek, sharedSecre
t)
end
[ADR] Encrypted Data Access and Key Delegation 12

---

<!-- PAGE 13 -->
## Page 13

rect rgb(255, 243, 224)
Note over User,Service: 2. USER DELEGATES TO AGENT SE
RVICE
User->>Service: AuthToken + EncryptionGrant<br/>subje
ct: 0xabc, bucketId: 123<br/>operations: [GET], canDelegate:
true<br/>expiresAt: now + 7 days<br/>constraints: maxDepth=1,
maxTTL=86400
end
rect rgb(243, 229, 245)
Note over Service: 3. AGENT SERVICE DERIVES AGENT KEY
S
Service->>Service: Decrypt DEK from Grant<br/>sharedS
ecret = X25519.ecdh(serviceKey, ephemeralPubKey)<br/>dek = AE
S-GCM.decrypt(encryptedDataKey, sharedSecret)
Service->>Service: Derive Agent-Specific Key<br/>agen
tNonce = crypto.randomBytes(16)<br/>agentDEK = HKDF(dek, "age
nt:" + agentId, agentNonce)
Service->>Agent: Create Agent Token with Derived Gran
t<br/>agentGrant = wrapDEK(agentDEK, agentKey.publicKey)
end
rect rgb(232, 245, 233)
Note over Agent: 4. AGENT ACCESSES ENCRYPTED DATA
Agent->>Agent: Receive Grant via context.encryption
Agent->>Agent: Decrypt DEK using derived key<br/>dek
= context.encryption.decryptDEK(grant)
Agent->>DDC: Fetch encrypted data<br/>ciphertext = co
ntext.storage.get(cid)
DDC-->>Agent: ciphertext
Agent->>Agent: Decrypt data<br/>plaintext = context.e
ncryption.decrypt(ciphertext, dek)
end
[ADR] Encrypted Data Access and Key Delegation 13

---

<!-- PAGE 14 -->
## Page 14

Token Specification
Extended Protobuf Definition
syntax = "proto3";
package ddc.auth;
option go_package = "cere.network/ddc-node/pb";
import "common/signature.proto";
// ==========================================================
===================
// CORE TOKEN STRUCTURES (Extended from existing AuthToken)
// ==========================================================
===================
message AuthToken {
common.Signature signature = 1;
Payload payload = 2;
}
message Payload {
// Existing fields (backward compatible)
optional AuthToken prev = 1;
optional bytes subject = 2;
optional bool canDelegate = 3;
optional uint64 bucketId = 4;
repeated Operation operations = 5;
optional int64 expiresAt = 6;
optional bytes pieceCid = 7;
// NEW: Encryption extension (field numbers 10+ for extensi
on)
[ADR] Encrypted Data Access and Key Delegation 14

---

<!-- PAGE 15 -->
## Page 15

optional EncryptionGrant encryptionGrant = 10;
}
enum Operation {
UNKNOWN = 0;
PUT = 1;
GET = 2;
DELETE = 3;
}
// ==========================================================
===================
// ENCRYPTION GRANT STRUCTURES
// ==========================================================
===================
message EncryptionGrant {
// Unique identifier for this key (hash of DEK + creation n
once)
bytes keyId = 1;
// How the DEK is accessed
oneof keyAccess {
// Option A: DEK directly encrypted for recipient (non-re
vocable)
EmbeddedKey embeddedKey = 2;
// Option B: Reference to Key Escrow Service (revocable)
KeyReference keyReference = 3;
}
// Constraints for key usage and delegation
DelegationConstraints constraints = 4;
// Proof of key derivation (for derived keys)
optional KeyDerivationProof derivationProof = 5;
[ADR] Encrypted Data Access and Key Delegation 15

---

<!-- PAGE 16 -->
## Page 16

// Encryption algorithm used for data
EncryptionAlgorithm dataEncryptionAlgorithm = 6;
}
message EmbeddedKey {
// DEK encrypted with recipient's X25519 public key via ECD
H
bytes encryptedDataKey = 1;
// Ephemeral public key used for ECDH (sender's ephemeral X
25519)
bytes ephemeralPubKey = 2;
// Nonce used for AES-GCM encryption of DEK
bytes nonce = 3;
}
message KeyReference {
// Key Escrow Service endpoint
string kesEndpoint = 1;
// Unique key identifier in KES
bytes keyId = 2;
// Policy ID for this specific grant (can be revoked)
bytes policyId = 3;
// Authorization proof (signed by key owner)
common.Signature authorizationProof = 4;
}
message DelegationConstraints {
// Maximum delegation depth from this point (0 = no further
delegation)
uint32 maxDepth = 1;
[ADR] Encrypted Data Access and Key Delegation 16

---

<!-- PAGE 17 -->
## Page 17

// Allowed operations for this grant and derived grants
repeated Operation allowedOperations = 2;
// Maximum TTL in seconds for derived grants
int64 maxTTL = 3;
// Specific agents allowed (empty = any agent under this se
rvice)
repeated bytes allowedAgents = 4;
// Whether key can be re-wrapped for other recipients
bool allowRewrap = 5;
}
message KeyDerivationProof {
// Parent key ID this was derived from
bytes parentKeyId = 1;
// Derivation algorithm
KeyDerivationAlgorithm algorithm = 2;
// Parameters used for derivation
bytes derivationParams = 3;
// Derived key public key (X25519)
bytes derivedPubKey = 4;
// Signature by parent key holder over derivation parameter
s
common.Signature derivationSignature = 5;
}
enum KeyDerivationAlgorithm {
KDA_UNKNOWN = 0;
KDA_HKDF_SHA256 = 1;
[ADR] Encrypted Data Access and Key Delegation 17

---

<!-- PAGE 18 -->
## Page 18

KDA_HKDF_SHA512 = 2;
}
enum EncryptionAlgorithm {
EA_UNKNOWN = 0;
EA_AES_256_GCM = 1;
EA_CHACHA20_POLY1305 = 2;
}
// ==========================================================
===================
// KEY ESCROW SERVICE MESSAGES
// ==========================================================
===================
message DepositKeyRequest {
// DEK encrypted with KES public key
bytes encryptedKey = 1;
// Ephemeral public key for ECDH
bytes ephemeralPubKey = 2;
// Owner's public key
bytes ownerPubKey = 3;
// Initial access policy
AccessPolicy initialPolicy = 4;
// Owner signature
common.Signature signature = 5;
}
message DepositKeyResponse {
// Assigned key ID
bytes keyId = 1;
}
[ADR] Encrypted Data Access and Key Delegation 18

---

<!-- PAGE 19 -->
## Page 19

message AccessPolicy {
repeated PolicyGrant grants = 1;
}
message PolicyGrant {
// Unique policy ID (for revocation)
bytes policyId = 1;
// Grantee public key
bytes subject = 2;
// Allowed operations
repeated Operation operations = 3;
// Expiration
int64 expiresAt = 4;
// Constraints for further delegation
DelegationConstraints constraints = 5;
// Status
GrantStatus status = 6;
// Created timestamp
int64 createdAt = 7;
}
enum GrantStatus {
GS_UNKNOWN = 0;
GS_ACTIVE = 1;
GS_REVOKED = 2;
GS_EXPIRED = 3;
}
message FetchKeyRequest {
[ADR] Encrypted Data Access and Key Delegation 19

---

<!-- PAGE 20 -->
## Page 20

// Key ID
bytes keyId = 1;
// Policy ID
bytes policyId = 2;
// Requester public key
bytes requesterPubKey = 3;
// Timestamp (for replay protection)
int64 timestamp = 4;
// Signature proving requester identity
common.Signature signature = 5;
}
message FetchKeyResponse {
// DEK encrypted for requester's X25519 key
bytes encryptedKey = 1;
// Ephemeral public key for ECDH
bytes ephemeralPubKey = 2;
// Nonce
bytes nonce = 3;
// Current constraints
DelegationConstraints constraints = 4;
}
message RevokeGrantRequest {
bytes keyId = 1;
bytes policyId = 2;
bytes ownerPubKey = 3;
common.Signature signature = 4;
}
[ADR] Encrypted Data Access and Key Delegation 20

---

<!-- PAGE 21 -->
## Page 21

message AddGrantRequest {
bytes keyId = 1;
PolicyGrant grant = 2;
bytes ownerPubKey = 3;
common.Signature signature = 4;
}
message ListGrantsRequest {
bytes keyId = 1;
bytes ownerPubKey = 2;
common.Signature signature = 3;
}
message ListGrantsResponse {
repeated PolicyGrant grants = 1;
}
Token Examples
Example 1: User Agent Service (Embedded Key)
→
{
"signature": {
"algorithm": "ED_25519",
"signer": "0x123...",
"value": "sig_bytes..."
},
"payload": {
"subject": "0xabc...",
"bucketId": 123,
"operations": ["GET"],
"canDelegate": true,
"expiresAt": 1735689600,
"encryptionGrant": {
[ADR] Encrypted Data Access and Key Delegation 21

---

<!-- PAGE 22 -->
## Page 22

"keyId": "key_abc123...",
"embeddedKey": {
"encryptedDataKey": "wrapped_dek_bytes...",
"ephemeralPubKey": "ephemeral_x25519_pubkey...",
"nonce": "random_12_bytes..."
},
"constraints": {
"maxDepth": 1,
"allowedOperations": ["GET"],
"maxTTL": 86400,
"allowRewrap": true
},
"dataEncryptionAlgorithm": "AES_256_GCM"
}
}
}
Example 2: User Agent Service (Key Reference - Revocable)
→
{
"signature": {
"algorithm": "ED_25519",
"signer": "0x123...",
"value": "sig_bytes..."
},
"payload": {
"subject": "0xabc...",
"bucketId": 123,
"operations": ["GET"],
"canDelegate": true,
"expiresAt": 1735689600,
"encryptionGrant": {
"keyId": "key_abc123...",
"keyReference": {
"kesEndpoint": "https://kes.cere.network",
[ADR] Encrypted Data Access and Key Delegation 22

---

<!-- PAGE 23 -->
## Page 23

"keyId": "key_abc123...",
"policyId": "policy_xyz789...",
"authorizationProof": {
"algorithm": "ED_25519",
"signer": "0x123...",
"value": "auth_sig..."
}
},
"constraints": {
"maxDepth": 1,
"allowedOperations": ["GET"],
"maxTTL": 86400
}
}
}
}
Example 3: Agent Service Agent (Derived Key)
→
{
"signature": {
"algorithm": "ED_25519",
"signer": "0xabc...",
"value": "sig_bytes..."
},
"payload": {
"prev": { /* Parent token from user */ },
"subject": null,
"operations": ["GET"],
"expiresAt": 1735603200,
"encryptionGrant": {
"keyId": "derived_key_agent1...",
"embeddedKey": {
"encryptedDataKey": "agent_wrapped_dek...",
"ephemeralPubKey": "agent_ephemeral_pubkey...",
[ADR] Encrypted Data Access and Key Delegation 23

---

<!-- PAGE 24 -->
## Page 24

"nonce": "agent_nonce..."
},
"constraints": {
"maxDepth": 0,
"allowedOperations": ["GET"],
"maxTTL": 3600,
"allowRewrap": false
},
"derivationProof": {
"parentKeyId": "key_abc123...",
"algorithm": "HKDF_SHA256",
"derivationParams": "agent:agent1:nonce123",
"derivedPubKey": "agent_derived_pubkey...",
"derivationSignature": {
"algorithm": "ED_25519",
"signer": "0xabc...",
"value": "derivation_sig..."
}
}
}
}
}
Key Management Options
Option A: Embedded Keys (Non-Revocable)
Flow:
flowchart LR
User[👤 User] --> Encrypt["🔐 Encrypt DEK with<br/>recipi
ent pubkey"]
Encrypt --> Embed["📦 Embed in token"]
Embed --> Send["📤 Send token"]
[ADR] Encrypted Data Access and Key Delegation 24

---

<!-- PAGE 25 -->
## Page 25

style User fill:#e3f2fd
style Encrypt fill:#fff3e0
style Embed fill:#f3e5f5
style Send fill:#e8f5e9
Pros:
Simple implementation
Offline operation (no network calls)
Fast (no KES latency)
Decentralized (no central service)
Cons:
Cannot revoke after token is issued
Recipient can store and reuse key after token expiration
No audit trail
Best For:
Short-lived grants (< 24 hours)
Low-sensitivity data
Scenarios where revocation is not critical
Implementation:
class EmbeddedKeyGrant {
async createGrant(
dek: CryptoKey,
recipientPubKey: Uint8Array,
constraints: DelegationConstraints
): Promise<EncryptionGrant> {
// Generate ephemeral X25519 keypair
const ephemeralKeyPair = await crypto.subtle.generateKey(
{ name: 'X25519' },
true,
[ADR] Encrypted Data Access and Key Delegation 25

---

<!-- PAGE 26 -->
## Page 26

['deriveBits']
);
// Derive shared secret via ECDH
const sharedSecret = await crypto.subtle.deriveBits(
{ name: 'X25519', public: recipientPubKey },
ephemeralKeyPair.privateKey,
256
);
// Encrypt DEK with shared secret
const nonce = crypto.getRandomValues(new Uint8Array(12));
const wrappedDEK = await crypto.subtle.encrypt(
{ name: 'AES-GCM', iv: nonce },
await crypto.subtle.importKey('raw', sharedSecret, 'AES
-GCM', false, ['encrypt']),
await crypto.subtle.exportKey('raw', dek)
);
return {
keyId: await this.computeKeyId(dek, nonce),
embeddedKey: {
encryptedDataKey: new Uint8Array(wrappedDEK),
ephemeralPubKey: await crypto.subtle.exportKey('raw',
ephemeralKeyPair.publicKey),
nonce: nonce,
},
constraints: constraints,
dataEncryptionAlgorithm: 'AES_256_GCM',
};
}
async decryptDEK(
grant: EncryptionGrant,
recipientPrivateKey: CryptoKey
): Promise<CryptoKey> {
[ADR] Encrypted Data Access and Key Delegation 26

---

<!-- PAGE 27 -->
## Page 27

// Derive shared secret
const sharedSecret = await crypto.subtle.deriveBits(
{ name: 'X25519', public: grant.embeddedKey.ephemeralPu
bKey },
recipientPrivateKey,
256
);
// Decrypt DEK
const dekBytes = await crypto.subtle.decrypt(
{ name: 'AES-GCM', iv: grant.embeddedKey.nonce },
await crypto.subtle.importKey('raw', sharedSecret, 'AES
-GCM', false, ['decrypt']),
grant.embeddedKey.encryptedDataKey
);
return crypto.subtle.importKey('raw', dekBytes, 'AES-GC
M', true, ['encrypt', 'decrypt']);
}
}
Option B: Key Escrow Service (Revocable)
Flow:
flowchart LR
User[👤 User] --> Deposit["📥 Deposit DEK in KES"]
Deposit --> Policy["📋 Create policy"]
Policy --> Issue["📤 Issue token with<br/>key reference"]
Policy --> Revoke["🚫 Revoke anytime"]
style User fill:#e3f2fd
style Deposit fill:#fff3e0
style Policy fill:#f3e5f5
[ADR] Encrypted Data Access and Key Delegation 27

---

<!-- PAGE 28 -->
## Page 28

style Issue fill:#e8f5e9
style Revoke fill:#ffcdd2
Architecture:
flowchart TB
subgraph KES["🏛 KEY ESCROW SERVICE (KES)"]
subgraph KeyStore["🔐 Key Store (HSM-backed)"]
Key001["Key 001<br/>(0x123)"]
Key002["Key 002<br/>(0x456)"]
Key003["Key 003<br/>(0x789)"]
end
subgraph PolicyStore["📋 Policy Store"]
Policy1["Key 001:<br/>├─ Policy A: subject=0xabc,
ops=[GET]<br/>│ expires=2024-12-31, status=ACTIVE<br/>└─ Pol
icy B: subject=0xdef, ops=[GET]<br/> expires=2024-06-30, st
atus=REVOKED"]
end
subgraph AuditLog["📜 Audit Log"]
Log1["2024-01-15 10:00:00 DEPOSIT key=001 owner=0
x123"]
Log2["2024-01-15 10:01:00 GRANT key=001 subject=0
xabc"]
Log3["2024-01-15 11:00:00 FETCH key=001 requester
=0xabc"]
Log4["2024-01-16 09:00:00 REVOKE key=001 policy=
B"]
end
end
style KES fill:#fafafa
style KeyStore fill:#e3f2fd
[ADR] Encrypted Data Access and Key Delegation 28

---

<!-- PAGE 29 -->
## Page 29

style PolicyStore fill:#fff3e0
style AuditLog fill:#f3e5f5
Pros:
Instant revocation
Full audit trail
Centralized policy management
Can update constraints without re-issuing tokens
Cons:
Requires KES availability
Single point of failure (mitigated with replication)
Network latency for key fetch
Operational overhead
Best For:
Long-lived grants (> 24 hours)
Sensitive data
Enterprise/compliance requirements
Scenarios requiring revocation
API Specification:
interface KeyEscrowService {
/**
* Deposit a DEK with initial access policy
*/
depositKey(request: {
encryptedKey: Uint8Array; // DEK encrypted with KES
public key
ephemeralPubKey: Uint8Array; // For ECDH
ownerPubKey: Uint8Array; // Owner's Ed25519 public
key
[ADR] Encrypted Data Access and Key Delegation 29

---

<!-- PAGE 30 -->
## Page 30

initialPolicy?: AccessPolicy; // Optional initial grant
s
signature: Signature; // Owner's signature
}): Promise<{ keyId: Uint8Array }>;
/**
* Add a new grant to existing key
*/
addGrant(request: {
keyId: Uint8Array;
grant: PolicyGrant;
ownerPubKey: Uint8Array;
signature: Signature;
}): Promise<{ policyId: Uint8Array }>;
/**
* Revoke an existing grant (immediate effect)
*/
revokeGrant(request: {
keyId: Uint8Array;
policyId: Uint8Array;
ownerPubKey: Uint8Array;
signature: Signature;
}): Promise<void>;
/**
* Update grant constraints
*/
updateGrant(request: {
keyId: Uint8Array;
policyId: Uint8Array;
updates: Partial<PolicyGrant>;
ownerPubKey: Uint8Array;
signature: Signature;
}): Promise<void>;
[ADR] Encrypted Data Access and Key Delegation 30

---

<!-- PAGE 31 -->
## Page 31

/**
* Fetch DEK (called by grantees)
*/
fetchKey(request: {
keyId: Uint8Array;
policyId: Uint8Array;
requesterPubKey: Uint8Array;
timestamp: number;
signature: Signature;
}): Promise<{
encryptedKey: Uint8Array;
ephemeralPubKey: Uint8Array;
nonce: Uint8Array;
constraints: DelegationConstraints;
}>;
/**
* List all grants for a key (owner only)
*/
listGrants(request: {
keyId: Uint8Array;
ownerPubKey: Uint8Array;
signature: Signature;
}): Promise<{ grants: PolicyGrant[] }>;
/**
* Get audit log for a key (owner only)
*/
getAuditLog(request: {
keyId: Uint8Array;
ownerPubKey: Uint8Array;
signature: Signature;
fromTime?: number;
toTime?: number;
[ADR] Encrypted Data Access and Key Delegation 31

---

<!-- PAGE 32 -->
## Page 32

}): Promise<{ entries: AuditEntry[] }>;
}
Option C: On-Chain Policy Registry
Flow:
flowchart LR
User[👤 User] --> Submit["📝 Submit grant<br/>to pallet"]
Submit --> OnChain["⛓ On-chain storage"]
OnChain --> Query["🔍 Storage nodes<br/>query chain"]
style User fill:#e3f2fd
style Submit fill:#fff3e0
style OnChain fill:#f3e5f5
style Query fill:#e8f5e9
Pallet Extension:
// Extend DDC pallet with encryption grants
#[pallet::storage]
pub type EncryptionGrants<T: Config> = StorageDoubleMap<
_,
Blake2_128Concat, KeyId,
Blake2_128Concat, PolicyId,
EncryptionGrantInfo<T>,
OptionQuery,
>;
#[derive(Encode, Decode, Clone, PartialEq, Eq, RuntimeDebug,
TypeInfo)]
pub struct EncryptionGrantInfo<T: Config> {
pub owner: T::AccountId,
pub subject: T::AccountId,
pub encrypted_dek: BoundedVec<u8, MaxDekSize>,
[ADR] Encrypted Data Access and Key Delegation 32

---

<!-- PAGE 33 -->
## Page 33

pub ephemeral_pubkey: [u8; 32],
pub operations: Operations,
pub expires_at: T::BlockNumber,
pub constraints: DelegationConstraints,
pub status: GrantStatus,
pub created_at: T::BlockNumber,
}
#[pallet::call]
impl<T: Config> Pallet<T> {
#[pallet::weight(10_000)]
pub fn create_encryption_grant(
origin: OriginFor<T>,
key_id: KeyId,
subject: T::AccountId,
encrypted_dek: BoundedVec<u8, MaxDekSize>,
ephemeral_pubkey: [u8; 32],
operations: Operations,
expires_at: T::BlockNumber,
constraints: DelegationConstraints,
) -> DispatchResult {
let who = ensure_signed(origin)?;
// Verify caller is key owner
ensure!(Self::is_key_owner(&who, &key_id), Error::<T
>::NotKeyOwner);
// Generate policy ID
let policy_id = Self::generate_policy_id(&key_id, &su
bject);
// Store grant
EncryptionGrants::<T>::insert(key_id, policy_id, Encr
yptionGrantInfo {
owner: who.clone(),
subject,
[ADR] Encrypted Data Access and Key Delegation 33

---

<!-- PAGE 34 -->
## Page 34

encrypted_dek,
ephemeral_pubkey,
operations,
expires_at,
constraints,
status: GrantStatus::Active,
created_at: <frame_system::Pallet<T>>::block_numb
er(),
});
Self::deposit_event(Event::EncryptionGrantCreated { k
ey_id, policy_id });
Ok(())
}
#[pallet::weight(5_000)]
pub fn revoke_encryption_grant(
origin: OriginFor<T>,
key_id: KeyId,
policy_id: PolicyId,
) -> DispatchResult {
let who = ensure_signed(origin)?;
// Verify caller is key owner
ensure!(Self::is_key_owner(&who, &key_id), Error::<T
>::NotKeyOwner);
// Update status to revoked
EncryptionGrants::<T>::mutate(key_id, policy_id, |may
be_grant| {
if let Some(grant) = maybe_grant {
grant.status = GrantStatus::Revoked;
}
});
Self::deposit_event(Event::EncryptionGrantRevoked { k
[ADR] Encrypted Data Access and Key Delegation 34

---

<!-- PAGE 35 -->
## Page 35

ey_id, policy_id });
Ok(())
}
}
Pros:
Fully decentralized
Immutable audit trail
No central point of failure
Cryptographically verifiable
Cons:
Transaction costs   0.01 CERE per operation)
Latency   6 seconds for finality)
On-chain storage costs
Less flexible updates
Best For:
High-value assets
Regulatory requirements for immutability
Cross-chain interoperability
Trustless environments
Option D: Hybrid (Recommended)
Combine the best of each approach:
interface HybridKeyManager {
/**
* Create grant with appropriate strategy based on requirem
ents
*/
[ADR] Encrypted Data Access and Key Delegation 35

---

<!-- PAGE 36 -->
## Page 36

createGrant(options: {
keyId: string;
subject: string;
// Strategy selection
strategy: 'embedded' | 'kes' | 'on-chain' | 'auto';
// Constraints
expiresIn: number;
operations: Operation[];
constraints: DelegationConstraints;
// Hints for 'auto' strategy
hints?: {
sensitivityLevel?: 'low' | 'medium' | 'high';
revocationRequired?: boolean;
auditRequired?: boolean;
};
}): Promise<AuthToken>;
}
// Auto-strategy selection logic
function selectStrategy(hints: StrategyHints): Strategy {
if (hints.sensitivityLevel === 'high' || hints.auditRequire
d) {
return 'on-chain';
}
if (hints.revocationRequired) {
return 'kes';
}
if (hints.expiresIn < 24 * 60 * 60 * 1000) { // < 24 hours
return 'embedded';
}
[ADR] Encrypted Data Access and Key Delegation 36

---

<!-- PAGE 37 -->
## Page 37

return 'kes'; // Default for longer-lived grants
}
Decision Matrix:
Requirement Embedded KES On-Chain
Short-lived   24h  ✅ Best ⚠ OK ❌ Slow
Revocable ❌ No ✅ Best ✅ Yes
Audit trail ❌ No ✅ Best ✅ Immutable
High availability ✅ Offline ⚠ Service SLA ✅ Blockchain
Low latency ✅ Best ⚠ Network ❌  6s
Decentralized ✅ Yes ❌ No ✅ Best
Cost ✅ Free ⚠ Service fee ⚠ Tx fee
SDK Integration
TypeScript SDK
import {
DdcClient,
AuthToken,
EncryptedDataManager,
KeyEscrowService,
Operation
} from '@cere-ddc-sdk/ddc-client';
// Initialize
const userSigner = new UriSigner('user_mnemonic...');
const ddc = await DdcClient.create(userSigner, TESTNET);
const kes = new KeyEscrowService({ endpoint: 'https://kes.cer
e.network' });
const edm = new EncryptedDataManager(ddc, kes, userSigner);
// ==========================================================
[ADR] Encrypted Data Access and Key Delegation 37

---

<!-- PAGE 38 -->
## Page 38

==
// 1. Upload Encrypted Data
// ==========================================================
==
const sensitiveData = new TextEncoder().encode('My secret dat
a');
const { cid, keyId } = await edm.uploadEncrypted({
data: sensitiveData,
bucketId: 123n,
// Optional initial grants
grants: [{
subject: '0xDataServiceA',
operations: [Operation.GET],
expiresIn: 7 * 24 * 60 * 60 * 1000, // 7 days
strategy: 'kes', // Revocable
constraints: {
maxDepth: 1,
maxAgentTTL: 3600,
},
}],
});
console.log('Encrypted data uploaded:', cid);
console.log('Key registered:', keyId);
// ==========================================================
==
// 2. Add Grant for New Data Service
// ==========================================================
==
const grantToken = await edm.addGrant({
keyId,
subject: '0xDataServiceB',
operations: [Operation.GET],
expiresIn: 30 * 24 * 60 * 60 * 1000, // 30 days
[ADR] Encrypted Data Access and Key Delegation 38

---

<!-- PAGE 39 -->
## Page 39

strategy: 'kes',
constraints: {
maxDepth: 0, // Cannot delegate to agents
},
});
console.log('Grant created for Service B:', grantToken.toStri
ng());
// ==========================================================
==
// 3. List Active Grants
// ==========================================================
==
const grants = await edm.listGrants(keyId);
console.log('Active grants:', grants);
// [
// { policyId: 'abc', subject: '0xDataServiceA', status: 'A
CTIVE', ... },
// { policyId: 'def', subject: '0xDataServiceB', status: 'A
CTIVE', ... }
// ]
// ==========================================================
==
// 4. Revoke Grant
// ==========================================================
==
await edm.revokeGrant({
keyId,
policyId: grants[0].policyId,
});
console.log('Grant revoked for Service A');
// ==========================================================
[ADR] Encrypted Data Access and Key Delegation 39

---

<!-- PAGE 40 -->
## Page 40

==
// 5. Update Grant Constraints
// ==========================================================
==
await edm.updateGrant({
keyId,
policyId: grants[1].policyId,
updates: {
expiresIn: 60 * 24 * 60 * 60 * 1000, // Extend to 60 days
},
});
console.log('Grant extended for Service B');
// ==========================================================
==
// 6. Get Audit Log
// ==========================================================
==
const auditLog = await edm.getAuditLog(keyId);
console.log('Key access history:', auditLog);
// [
// { timestamp: ..., action: 'DEPOSIT', owner: '0x123' },
// { timestamp: ..., action: 'GRANT', subject: '0xServiceA'
},
// { timestamp: ..., action: 'FETCH', requester: '0xService
A' },
// { timestamp: ..., action: 'REVOKE', policyId: 'abc' },
// ]
Agent Service SDK
import { DataServiceClient, KeyDerivationService } from '@cer
e-ddc-sdk/data-service';
[ADR] Encrypted Data Access and Key Delegation 40

---

<!-- PAGE 41 -->
## Page 41

// Data Service receives grant from user
const userGrantToken = AuthToken.from(receivedTokenString);
// Initialize
const serviceSigner = new UriSigner('service_mnemonic...');
const kds = new KeyDerivationService(serviceSigner);
// ==========================================================
==
// 1. Decrypt User's DEK
// ==========================================================
==
const dek = await kds.decryptDEK(userGrantToken.encryptionGra
nt);
// ==========================================================
==
// 2. Derive Key for Specific Agent
// ==========================================================
==
const agentId = 'sentiment-analyzer';
const agentGrant = await kds.deriveAgentGrant({
parentGrant: userGrantToken.encryptionGrant,
agentId: agentId,
expiresIn: 3600 * 1000, // 1 hour
});
// ==========================================================
==
// 3. Create Agent Token
// ==========================================================
==
const agentToken = new AuthToken({
prev: userGrantToken,
operations: [Operation.GET],
expiresIn: 3600 * 1000,
[ADR] Encrypted Data Access and Key Delegation 41

---

<!-- PAGE 42 -->
## Page 42

encryptionGrant: agentGrant,
});
await agentToken.sign(serviceSigner);
// Pass token to agent via execution context
await orchestrator.executeAgent({
agentId: agentId,
event: { payload: { cid: 'data_cid...' } },
context: {
encryptionGrant: agentGrant,
authToken: agentToken.toString(),
},
});
Agent Context API
// Agent code running in V8 isolate
async function handle(event: any, ctx: any) {
// ========================================================
====
// 1. Get Encryption Grant from Context
// ========================================================
====
const grant = ctx.encryption.getGrant();
if (!grant) {
ctx.log('No encryption grant provided');
return { error: 'Missing encryption grant' };
}
// ========================================================
====
// 2. Decrypt DEK Using Derived Key
// ========================================================
[ADR] Encrypted Data Access and Key Delegation 42

---

<!-- PAGE 43 -->
## Page 43

====
const dek = await ctx.encryption.decryptDEK(grant);
// ========================================================
====
// 3. Fetch Encrypted Data
// ========================================================
====
const encryptedData = await ctx.storage.get(event.payload.c
id);
// ========================================================
====
// 4. Decrypt Data
// ========================================================
====
const plainData = await ctx.encryption.decrypt(encryptedDat
a, dek);
// ========================================================
====
// 5. Process Data
// ========================================================
====
const result = await ctx.models.infer('gpt-4', {
prompt: 'Analyze this data',
data: new TextDecoder().decode(plainData),
});
return { analysis: result };
}
Storage Node Verification
[ADR] Encrypted Data Access and Key Delegation 43

---

<!-- PAGE 44 -->
## Page 44

// Extended gater.go for encryption grant verification
func (g *gater) expandAndVerifyToken(token *pb.AuthToken, exp
anded *ExpandedToken, depth int) error {
// ... existing verification ...
// Verify encryption grant if present
if token.Payload.EncryptionGrant != nil {
if err := g.verifyEncryptionGrant(token, expanded, de
pth); err != nil {
return fmt.Errorf("encryption grant verification
failed: %w", err)
}
}
// Continue to parent token
if token.Payload.Prev != nil {
return g.expandAndVerifyToken(token.Payload.Prev, exp
anded, depth+1)
}
return nil
}
func (g *gater) verifyEncryptionGrant(token *pb.AuthToken, ex
panded *ExpandedToken, depth int) error {
grant := token.Payload.EncryptionGrant
// 1. Verify constraints
if grant.Constraints.MaxDepth < uint32(depth) {
return ErrDelegationDepthExceeded
}
// 2. Verify operations subset
if !operationsSubset(grant.Constraints.AllowedOperations,
token.Payload.Operations) {
[ADR] Encrypted Data Access and Key Delegation 44

---

<!-- PAGE 45 -->
## Page 45

return ErrInvalidGrantOperations
}
// 3. Verify TTL constraint
tokenTTL := token.Payload.ExpiresAt - time.Now().Unix()
if tokenTTL > grant.Constraints.MaxTTL {
return ErrGrantTTLExceeded
}
// 4. Verify key reference if using KES
if grant.KeyReference != nil {
if err := g.verifyKeyReference(grant.KeyReference); e
rr != nil {
return err
}
}
// 5. Verify derivation proof if derived key
if grant.DerivationProof != nil {
if err := g.verifyDerivationProof(grant.DerivationPro
of, expanded.parentKeyId); err != nil {
return err
}
}
// 6. Store key ID for activity capture
expanded.keyId = grant.KeyId
return nil
}
func (g *gater) verifyKeyReference(ref *pb.KeyReference) erro
r {
// Query KES to verify policy is active
client := g.kesClients[ref.KesEndpoint]
if client == nil {
[ADR] Encrypted Data Access and Key Delegation 45

---

<!-- PAGE 46 -->
## Page 46

return ErrUnknownKES
}
status, err := client.GetPolicyStatus(ref.KeyId, ref.Poli
cyId)
if err != nil {
return fmt.Errorf("KES query failed: %w", err)
}
if status != pb.GrantStatus_GS_ACTIVE {
return ErrGrantRevoked
}
return nil
}
func (g *gater) verifyDerivationProof(proof *pb.KeyDerivation
Proof, expectedParentKeyId []byte) error {
// 1. Verify parent key ID matches
if !bytes.Equal(proof.ParentKeyId, expectedParentKeyId) {
return ErrInvalidDerivationParent
}
// 2. Verify derivation signature
message := append(proof.DerivedPubKey, proof.DerivationPa
rams...)
valid, err := pb.VerifySignatureBytes(
proof.DerivationSignature.Signer,
message,
proof.DerivationSignature.Value,
proof.DerivationSignature.Algorithm,
)
if err != nil || !valid {
return ErrInvalidDerivationSignature
}
[ADR] Encrypted Data Access and Key Delegation 46

---

<!-- PAGE 47 -->
## Page 47

return nil
}
Implementation Phases
Phase 1: Core Encryption (4 weeks)
Deliverables:
- [ ] interface in SDK
Cipher
- [ ] AES 256 GCM implementation
- [ ] Encrypt/decrypt in /
upload() download()
- [ ] CLI flags: ,
--encrypt --key
- [ ] Unit and integration tests
Files Modified:
-
packages/ddc/src/encryption/Cipher.ts
-
packages/ddc/src/encryption/AesGcmCipher.ts
-
packages/ddc/src/DdcClient.ts
-
packages/cli/src/commands/upload.ts
-
packages/cli/src/commands/download.ts
Phase 2: Encryption Grant in Token (3 weeks)
Deliverables:
- [ ] Extended protobuf definitions
- [ ] creation in SDK
EncryptionGrant
- [ ] implementation
EmbeddedKey
- [ ] Token serialization with grants
- [ ] Update storage node for grant verification
Files Modified:
-
packages/ddc/protos/auth_token.proto
-
packages/ddc/src/auth/AuthToken.ts
-
packages/ddc/src/auth/EncryptionGrant.ts
-
internal/storage/auth/gater.go
Phase 3: Key Derivation (2 weeks)
[ADR] Encrypted Data Access and Key Delegation 47

---

<!-- PAGE 48 -->
## Page 48

Deliverables:
- [ ] HKDF implementation
- [ ] Agent key derivation
- [ ] generation and verification
KeyDerivationProof
- [ ] Data service SDK support
Files Modified:
-
packages/ddc/src/encryption/KeyDerivation.ts
-
packages/ddc/src/encryption/DerivationProof.ts
Phase 4: Key Escrow Service (4 weeks)
Deliverables:
- [ ] KES API specification
- [ ] KES server implementation
- [ ] SDK client for KES
- [ ] Grant lifecycle management (add/revoke/update)
- [ ] Audit logging
New Components:
- - Key Escrow Service
services/kes/
-
packages/ddc/src/kes/KeyEscrowClient.ts
Phase 5: Agent Runtime Integration (3 weeks)
Deliverables:
- [ ] API in agent runtime
context.encryption
- [ ] wrapper
context.secureStorage
- [ ] Grant injection via execution context
- [ ] V8 crypto bindings
Files Modified:
-
internal/compute/agentruntime/context/encryption.go
-
internal/compute/agentruntime/context/builder.go
-
internal/compute/agentruntime/shared/types.go
Phase 6: On-Chain Registry (Optional, 4 weeks)
Deliverables:
- [ ] Pallet extension for encryption grants
[ADR] Encrypted Data Access and Key Delegation 48

---

<!-- PAGE 49 -->
## Page 49

- [ ] On-chain grant management
- [ ] Storage node blockchain query integration
- [ ] Migration tools
Files Modified:
-
pallets/ddc/src/lib.rs
-
internal/storage/blockchain/indexer.go
Security Considerations
Threat Model
Threat Mitigation
Compromised storage node Data encrypted client-side; nodes never see plaintext
Keys never transmitted in plaintext; always wrapped via
Key theft
ECDH
Replay attacks Timestamps and nonces in key fetch requests
Privilege escalation Constraint validation at each delegation level
Unauthorized revocation Owner signature required for all KES operations
KES compromise DEKs encrypted at rest; HSM for key storage
Agent key leakage Derived keys are short-lived and scoped
Cryptographic Choices
Component Algorithm Rationale
Data encryption AES 256 GCM AEAD, hardware acceleration
Key exchange X25519  ECDH  Fast, secure, compatible with Ed25519
Key derivation HKDF SHA256 RFC 5869, deterministic
Signing Ed25519 Fast, small signatures
Key ID BLAKE3 Fast, collision resistant
Key Rotation
[ADR] Encrypted Data Access and Key Delegation 49

---

<!-- PAGE 50 -->
## Page 50

interface KeyRotationPolicy {
// Maximum key age before rotation required
maxKeyAge: Duration;
// Grace period for old keys after rotation
gracePeriod: Duration;
// Automatic rotation trigger
autoRotate: boolean;
// Notification webhook for rotation events
notifyUrl?: string;
}
async function rotateKey(keyId: string, policy: KeyRotationPo
licy): Promise<string> {
// 1. Generate new DEK
const newDEK = await generateDEK();
// 2. Fetch current grants
const grants = await kes.listGrants(keyId);
const activeGrants = grants.filter(g => g.status === 'ACTIV
E');
// 3. Re-wrap DEK for all active grantees
const newGrants = await Promise.all(
activeGrants.map(async (grant) => ({
...grant,
encryptedDataKey: await wrapDEK(newDEK, grant.subject),
}))
);
// 4. Deposit new key with migrated grants
const newKeyId = await kes.depositKey({
key: newDEK,
[ADR] Encrypted Data Access and Key Delegation 50

---

<!-- PAGE 51 -->
## Page 51

owner: ownerPubKey,
initialPolicy: { grants: newGrants },
});
// 5. Re-encrypt data (if required)
if (policy.reEncryptData) {
await reEncryptData(keyId, newKeyId);
}
// 6. Schedule old key deletion after grace period
await kes.scheduleKeyDeletion(keyId, policy.gracePeriod);
return newKeyId;
}
Consequences
Positive
   Privacy by Default: User data encrypted at rest; storage nodes cannot read
content
   Flexible Access Control: Multiple key management strategies for different
requirements
   Hierarchical Delegation: Clean user → service → agent key hierarchy
   Revocability: Can revoke access to existing encrypted data (with KES 
   Audit Trail: Full visibility into key access patterns
   Backward Compatibility: Encryption is optional; existing tokens continue to
work
   Unified Pattern: Same authorization model for storage and compute
Negative
[ADR] Encrypted Data Access and Key Delegation 51

---

<!-- PAGE 52 -->
## Page 52

   Complexity: Additional cryptographic operations increase implementation
complexity
   Performance: Encryption adds  5% overhead; KES adds network latency
   Key Management: Users must securely store their master keys
   Recovery: Lost DEK means data is permanently inaccessible
   KES Dependency: Revocable grants require KES availability
Risks
Risk Likelihood Impact Mitigation
Replicated deployment; fallback
KES downtime Medium High
to embedded keys
Key backup guidance; recovery
Key loss Low Critical
phrases
Cryptographic Use standard algorithms;
Low Critical
vulnerability security audits
Performance
Medium Medium Hardware acceleration; caching
degradation
References
    ADR  Authentication and authorization - Existing DDC auth system
   RFC 5869   HKDF  HMAC-based Key Derivation Function)
   RFC 7748   Elliptic Curves for Security  X25519 
   RFC 5116   AEAD  AES GCM 
Appendix A: Cryptographic Primitives
A.1 Key Generation
// Generate Ed25519 signing key
async function generateSigningKey(): Promise<CryptoKeyPair> {
[ADR] Encrypted Data Access and Key Delegation 52

---

<!-- PAGE 53 -->
## Page 53

return crypto.subtle.generateKey(
{ name: 'Ed25519' },
true,
['sign', 'verify']
);
}
// Derive X25519 encryption key from Ed25519
async function deriveEncryptionKey(ed25519Private: CryptoKe
y): Promise<CryptoKeyPair> {
// Ed25519 private key can be converted to X25519
// See: https://doc.libsodium.org/advanced/ed25519-curve255
19
const rawKey = await crypto.subtle.exportKey('raw', ed25519
Private);
const x25519Private = ed25519ToX25519(rawKey);
return crypto.subtle.importKey('raw', x25519Private, 'X2551
9', true, ['deriveBits']);
}
// Generate DEK
async function generateDEK(): Promise<CryptoKey> {
return crypto.subtle.generateKey(
{ name: 'AES-GCM', length: 256 },
true,
['encrypt', 'decrypt']
);
}
A.2 ECDH Key Exchange
async function wrapDEK(
dek: CryptoKey,
recipientPubKey: Uint8Array
): Promise<{ wrapped: Uint8Array; ephemeralPub: Uint8Array; n
[ADR] Encrypted Data Access and Key Delegation 53

---

<!-- PAGE 54 -->
## Page 54

once: Uint8Array }> {
// Generate ephemeral keypair
const ephemeral = await crypto.subtle.generateKey(
{ name: 'X25519' },
true,
['deriveBits']
);
// ECDH to derive shared secret
const recipientKey = await crypto.subtle.importKey(
'raw',
recipientPubKey,
{ name: 'X25519' },
false,
[]
);
const sharedSecret = await crypto.subtle.deriveBits(
{ name: 'X25519', public: recipientKey },
ephemeral.privateKey,
256
);
// Derive wrapping key via HKDF
const wrappingKey = await crypto.subtle.importKey(
'raw',
sharedSecret,
'AES-GCM',
false,
['encrypt']
);
// Wrap DEK
const nonce = crypto.getRandomValues(new Uint8Array(12));
const dekBytes = await crypto.subtle.exportKey('raw', dek);
const wrapped = await crypto.subtle.encrypt(
[ADR] Encrypted Data Access and Key Delegation 54

---

<!-- PAGE 55 -->
## Page 55

{ name: 'AES-GCM', iv: nonce },
wrappingKey,
dekBytes
);
return {
wrapped: new Uint8Array(wrapped),
ephemeralPub: new Uint8Array(await crypto.subtle.exportKe
y('raw', ephemeral.publicKey)),
nonce: nonce,
};
}
A.3 HKDF Key Derivation
async function deriveAgentKey(
masterKey: CryptoKey,
agentId: string,
nonce: Uint8Array
): Promise<CryptoKey> {
const masterKeyBytes = await crypto.subtle.exportKey('raw',
masterKey);
// HKDF-SHA256
const hkdfKey = await crypto.subtle.importKey(
'raw',
masterKeyBytes,
'HKDF',
false,
['deriveBits', 'deriveKey']
);
const info = new TextEncoder().encode(`agent:${agentId}`);
return crypto.subtle.deriveKey(
[ADR] Encrypted Data Access and Key Delegation 55

---

<!-- PAGE 56 -->
## Page 56

{
name: 'HKDF',
hash: 'SHA-256',
salt: nonce,
info: info,
},
hkdfKey,
{ name: 'AES-GCM', length: 256 },
true,
['encrypt', 'decrypt']
);
}
Appendix B: Error Codes
Code Name Description
E_GRANT_EXPIRED Grant Expired Encryption grant has expired
E_GRANT_REVOKED Grant Revoked Encryption grant was revoked
E_DEPTH_EXCEEDED Delegation Depth Exceeded Too many delegation levels
E_TTL_EXCEEDED TTL Exceeded Token TTL exceeds grant constraint
E_INVALID_DERIVATION Invalid Derivation Key derivation proof is invalid
E_KEY_NOT_FOUND Key Not Found Key ID not found in KES
E_POLICY_NOT_FOUND Policy Not Found Policy ID not found
E_UNAUTHORIZED Unauthorized Requester not authorized for key
E_INVALID_SIGNATURE Invalid Signature Signature verification failed
E_KES_UNAVAILABLE KES Unavailable Key Escrow Service unreachable
[ADR] Encrypted Data Access and Key Delegation 56


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DDC transmits data in plaintext by default -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

DDC transmits data in plaintext by default. Storage Nodes and CDN Nodes handle the storage, retrieval, and distribution of objects, files, and documents without applying encryption at the transport layer unless explicitly configured. CDN Nodes leverage internal memory and physical resources as isolated software instances, meaning plaintext data may be processed and cached in memory during read and write operations. Applications requiring confidentiality should implement encryption at the client layer before submitting data to the cluster, as DDC does not enforce encryption by default across node operations.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Authentication is handled entirely on the client side in DDC -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Authentication is handled entirely on the client side -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Authentication in DDC is handled entirely on the client side prior to request submission. DDC nodes enforce authentication at the node level by verifying request signatures against the user identity, ensuring that only valid, signed requests are processed. Authorization is governed by bucket permissions, allowing nodes to independently validate access rights without requiring continuous connectivity to the blockchain. This architecture enables DDC nodes to operate as autonomous participants within the distributed storage layer, processing and verifying storage requests in a trustless manner consistent with the network's decentralized design principles.

<!-- EDIT-END: Q3 -->


Authentication in DDC is handled at the node level rather than exclusively on the client side. Each DDC node independently verifies incoming storage requests by validating request signatures against the user's identity, allowing nodes to authenticate and authorize requests without requiring continuous blockchain connectivity. Authorization is further governed by bucket permissions, enabling fine-grained access control within the distributed storage layer. This architecture allows DDC nodes to operate as independent participants capable of enforcing security policies locally while remaining part of a trustless, decentralized data infrastructure.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The trust chain cannot be broken -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://genspect.org/the-broken-chain-of-trust-medicines-crisis-of-credibility/] | [external: https://www.esignglobal.com/blog/fixing-broken-trust-chain-pdf] | [external: https://en.wikipedia.org/wiki/Chain_of_trust] -->

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The trust chain cannot be broken -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.tenable.com/plugins/nessus/51192] | [external: https://www.appviewx.com/blogs/what-happens-when-a-certificate-chain-of-trust-breaks/] | [external: https://serverfault.com/questions/676070/is-this-ssl-certificate-chain-broken-and-how-to-fix-it] -->

The trust chain in DDC is anchored to your data wallet keypair, which serves as your cryptographic identity within the ecosystem. Every operation, from signing requests to delegating access permissions, must be traceable back to this root identity. If any link in this chain is absent or unverifiable, authentication fails and access is denied. This design ensures that no interaction within a DDC cluster can be authorized without a continuous, unbroken chain of cryptographic accountability from the originating data wallet through to the target resource.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The trust chain cannot be broken -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://genspect.org/the-broken-chain-of-trust-medicines-crisis-of-credibility/] | [external: https://www.esignglobal.com/blog/fixing-broken-trust-chain-pdf] | [external: https://en.wikipedia.org/wiki/Chain_of_trust] -->

Token-based grants in DDC are non-revocable once issued. To bound their validity window, each grant carries an expiration time, which limits but does not eliminate replay attack risk. Protocol implementations must honor issued tokens until expiration, and clients connecting through such grants are responsible for evaluating the trust implications of this model. The finite validity period should be treated as a mitigation measure, not a guarantee of revocation capability. Deployments requiring stricter access control must account for this constraint when designing authorization flows.

<!-- EDIT-END: Q3 -->


Token-based grants in DDC are non-revocable once issued. To bound their validity window, each grant carries an expiration time, which limits but does not eliminate replay attack risk. Protocol implementations must honor issued tokens until expiration, and this finite validity period should be treated as a security boundary rather than a revocation mechanism. Clients connecting through such grants are responsible for evaluating the trust implications of this model. The trust chain therefore depends on expiration enforcement as its primary integrity control, and any lapse in that enforcement breaks the chain of trust for downstream participants.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The account used to create the instance should have positive balance -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The account used to create the instance should have positive balance and DDC deposit -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Before initializing the DDC client, ensure the account associated with the provided seed phrase meets two prerequisites: it must hold a positive token balance and an active DDC deposit. Without these, client instantiation will succeed but subsequent operations such as bucket creation will fail. To set up the account, fund it through the Cere Network and register the required DDC deposit via the network's smart contracts. Only after both conditions are satisfied should you proceed to call DdcClient.create with your seed phrase and target network configuration.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The account used to create the instance should have DDC deposit -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Before initializing the DDC client, ensure the account associated with the provided seed phrase carries both a positive token balance and an active DDC deposit. Without these prerequisites, the client instance will lack the necessary authorization to interact with the network. The DDC deposit functions as a commitment to the decentralized data infrastructure, distinct from the general account balance. In the example above, the seed phrase identifies the account, so verify deposit status for that specific account before proceeding to operations such as bucket creation.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The account used to create the instance should have DDC deposit -->
<!-- SOURCES: [internal: DDC Client JS SDK Wiki.pdf (11 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Before initializing the DDC client, ensure the account associated with the provided seed phrase meets two prerequisites: a positive token balance and an active DDC deposit. The DDC deposit is separate from the general account balance and is required to interact with DDC storage resources such as creating buckets or uploading data. Without both conditions met, client operations will fail at runtime. To set up the deposit, use the Cere Network hub or the appropriate on-chain extrinsic before invoking DdcClient.create() with your seed and target network configuration.

<!-- EDIT-END: Q3 -->


Before initializing the DDC client, ensure the account associated with the provided seed phrase holds a positive balance and an active DDC deposit. Without both conditions met, the client instance will lack the necessary permissions to interact with the network. In the example above, the seed phrase identifies the account used to authenticate all subsequent operations, including bucket creation and data upload. Funding the account and establishing a DDC deposit are prerequisite steps that must be completed before invoking DdcClient.create.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Authentication and access control functions degrade gracefully during control plane disruptions -->
<!-- SOURCES: [internal: ADR ] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Authentication and access control functions in DDC are designed to remain operational during disruptions to the control plane. Authorized access is enforced through a combination of smart contracts and decentralized mechanisms, ensuring that credential validation and permission checks do not rely on a single point of coordination. When control plane availability is degraded, nodes continue to apply locally cached access policies, allowing read and write operations for authenticated principals to proceed without interruption. This separation of the authorization enforcement path from centralized control ensures continuity of data access under adverse network conditions.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: No single service provider controls the authoritative configuration state in DDC -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: No single service provider controls the authoritative configuration state, eliminating vendor lock-in -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Cluster configuration states and their corresponding validation outcomes are permanently recorded on a decentralized ledger, produced by the DAC Core and Validation layer. Because no single service provider controls the authoritative configuration state, operators are not subject to vendor lock-in and retain full flexibility over their infrastructure decisions. This transparency is enforced at the protocol level, meaning any party can inspect configuration records without relying on a privileged intermediary to attest to their accuracy.

<!-- EDIT-END: Q2 -->


Cluster configuration states and their corresponding validation outcomes are permanently recorded on a decentralized ledger, produced by the DAC Core and Validation layer. Because no single service provider controls the authoritative configuration state, operators are protected from vendor lock-in and retain full flexibility over their infrastructure. These records remain transparently accessible to any authorized party, ensuring that configuration authority is distributed across the network rather than concentrated within any one provider or administrative entity.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DDC trust chain cannot be broken -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The DDC authentication model implements a recursive JWT-like token structure that functions as a verifiable trust chain. Each token can be signed and delegated to downstream clients, with the option to attach additional claims that are scoped more narrowly than the permissions originally granted. This design ensures that any client presenting a token to the DDC can be cryptographically traced back through the chain of delegating parties, preserving end-to-end accountability without requiring a centralized authority to validate each hop in the authorization path.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The signature scheme uses sr25519 -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

DDC employs sr25519 as its signature scheme for authenticating client requests within the cluster. Each request must include metadata and a valid signature, which serves as cryptographic proof that the client both originated the request and holds the necessary access rights to the target content. This design ensures that requests cannot be forged or replayed, and allows nodes to distinguish between direct client connections and those proxied through CDN infrastructure. The signature verification step is a core component of DDC's authorization flow, enforced at the node level before any data access is granted.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The encryption-before-upload step is described in multiple ADRs but is not integrated into the Get Started guide's step- -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html] | [external: https://www.cyber.gc.ca/en/guidance/data-transfer-upload-protection-itsap40212] | [external: https://docs.nextcloud.com/server/32/admin_manual/configuration_files/encryption_configuration.html] -->

Step 7: Encrypt Before Upload

DDC enforces data security at the node level through signature verification, but does not apply encryption to content in transit or at rest on your behalf. Before calling the upload API, encrypt your payload using application-layer encryption on the client side. This ensures that even if access controls are misconfigured or a node is compromised, raw content remains unreadable. Passing unencrypted data directly to the upload method will store it in plaintext across the cluster, which is not appropriate for sensitive or production workloads.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Requests cannot be forged, as the signature cryptographically binds the client's identity to the specific request parame -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://republic.com/cere] | [external: https://github.com/Cerebellum-Network/docs.cere.network] | [external: https://www.cere.network/blog/cere-partnerships-overview-c1862] -->

Each request submitted to a DDC cluster must include metadata and a valid signature, which serves as cryptographic proof that the client both originated the request and holds the necessary access rights to the target content. This signature cryptographically binds the client's identity to the specific request parameters, ensuring that requests cannot be forged or replayed. Nodes use this mechanism to verify authenticity directly, distinguishing between requests originating from clients and those proxied through CDN infrastructure, without relying on any centralized authority to validate access.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: ** No explicit comparison of DDC's security guarantees with specific security controls offered by Databricks/Snowflake. -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

DDC enforces data security through client-side key custody, request signing, and node-level signature verification prior to any data access. The following categories provide a basis for comparing DDC controls against equivalent capabilities in centralized data platforms: encryption at rest, where DDC encrypts data before it leaves the client; key management, where private keys remain exclusively under client control and are never transmitted to or stored by cluster nodes; access auditing, where signed request verification creates a tamper-evident authorization record at the node layer; and compliance certification, which remains an independent evaluation responsibility for each deploying organization.

<!-- EDIT-END: Q2 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The signature format is signatureBytes = sr25519($requestId$bucketId$timestamp$userPublicKey) -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Each authenticated client request to DDC must include a signature that authorizes access to the requested content. The signature is computed using the sr25519 algorithm over the concatenated fields: requestId, bucketId, timestamp, and the user's public key, producing the signatureBytes value. This construction ensures that requests cannot be forged, as the signature cryptographically binds the client's identity to the specific request parameters. DDC nodes use this signature to distinguish direct client requests from those proxied by CDN nodes, enabling accurate activity capture and authorization enforcement across the cluster.

<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The signature is computed using sr25519 over concatenated fields: requestId, bucketId, timestamp, and userPublicKey -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

When constructing an authenticated request to a DDC node, the client produces a signature over a concatenated set of fields: the requestId, bucketId, timestamp, and userPublicKey. This signature is computed using the sr25519 signing scheme. The resulting signed payload allows DDC nodes to verify that a request originates from a legitimate client, confirm the client holds access rights to the specified bucket, and ensure the request cannot be forged or replayed. Requests that cannot be verified against these fields are rejected, distinguishing authenticated client requests from other traffic such as requests proxied through CDN nodes.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The signature is encoded as signature = base58(signatureBytes) -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The signature field in an authenticated DDC request is encoded using Base58 representation of the raw signature bytes, expressed as signature = base58(signatureBytes). This encoding is consistent with the broader DDC authentication model, in which client requests carry metadata and signatures that authorize access to content. The encoded signature serves as cryptographic proof that the request originated from a legitimate client, ensuring that no party can forge or replay a valid request without possession of the corresponding private key credentials.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The signature is computed using sr25519 over concatenated fields: signatureBytes = sr25519($requestId$bucketId$timestamp -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

To authorize a request, the client constructs a signature over a concatenated set of fields: the request identifier, bucket identifier, timestamp, and the user public key. This signature is computed using the sr25519 signing scheme. The resulting signed payload allows CDN and DAC nodes to verify that the request originates from a legitimate client, distinguishing direct client requests from those proxied by CDN nodes. Because the signature cryptographically binds the client's public key to the specific request parameters, it is not possible to forge or replay a valid authorization without possession of the corresponding private key.

<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Only pallet-based access is revocable in DDC -->
<!-- SOURCES: [internal: Encrypted Data Access and Key Delegation.pdf (56 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Access control in DDC operates under an important revocability constraint: only pallet-based access grants can be revoked after issuance. Shared link tokens and similar credential types carry expiration times to bound their validity window but cannot be individually revoked once issued. Because each authorization is cryptographically bound to the client's public key and to specific request parameters, forging or replaying a valid credential without the corresponding private key is not possible. Applications requiring immediate revocation of access should therefore rely on pallet-based grants rather than token-based credentials.

<!-- EDIT-END: Q2 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Only pallet based access is revocable -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.txcourts.gov/media/1458728/220953pc.pdf] | [external: https://www.hope-causey.com/blog/texas-supreme-court-rules-on-whether-pallet-in-supermarket-was-unreasonably-dangerous-in-6-million-slip-and-fall-case/] | [external: https://www.logecamps.com/terms-and-conditions] -->

Access control in DDC operates under an important revocability constraint: only pallet-based access grants can be revoked after issuance. Shared link tokens and similar credential types carry expiration times to bound their validity window, but cannot be actively revoked before expiration. This distinction has direct security implications. Shared links may be vulnerable to replay attacks within their validity period, and the decision to trust node responses derived from such credentials is delegated to the client. Systems requiring guaranteed revocation of access must rely exclusively on pallet-based authorization mechanisms.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Authentication gater uses bucket and customer indexes persisted on disk -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The authentication gater verifies customer balance and debt before granting access to DDC resources. To support this, customer and bucket indexes are persisted on disk, allowing the gater to query account state without relying solely on real-time blockchain lookups. This approach bridges the gap while blockchain-native indexes for customer balance and debt data remain under active development. The on-disk indexes are populated through blockchain event listeners that track relevant state changes, ensuring the gater operates against a locally consistent view of customer account data.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DDC's security advantages over centralized storage stacks are conditional on verified operator independence -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://cdn.prod.website-files.com/65324127b919c1e8fc21a198/65aa4ea7a3b9b7df623dc2f8_Cere%20LitePaper%20V1.0.pdf] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

DDC's security advantages over centralized storage stacks are conditional on verified operator independence. The erasure coding reconstruction threshold allows original data to be recovered without coordinating with any external party, and the fragmentation model limits data availability to colluding operators. However, fragmentation alone does not constitute a confidentiality control. Deployments with confidentiality requirements should account for the trust assumptions placed on individual node operators, as the integrity of the security model depends on the absence of coordinated collusion across the cluster.

<!-- EDIT-END: Q2 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: Erasure coding in DDC is a fault-tolerance mechanism, not a confidentiality control -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://ukulililixl.github.io/_pages/files/tc23rackcu.pdf] | [external: https://docs.ceph.com/en/reef/rados/operations/erasure-code/] | [external: https://www.mdpi.com/2076-3417/13/4/2170] -->

Erasure coding in DDC is a fault-tolerance mechanism, not a confidentiality control. Data is split into k data chunks and m parity chunks according to a configurable k:m policy, then distributed across storage nodes in the cluster. This redundancy allows the system to reconstruct original data even when up to m nodes become unavailable, without storing full replicas on every node. Because erasure coding operates on plaintext fragments, it provides no protection against unauthorized data access. Confidentiality requires separate controls such as encryption, applied independently of the erasure coding layer.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DDC separates cloud infrastructure & operations from the protocol -->
<!-- SOURCES: [internal: DDC from Sergey Poluyan.pdf (21 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

DDC enforces a clean separation between cloud infrastructure and operations on one side, and the underlying protocol on the other. The tools and services provided by Cere implement this boundary explicitly, allowing specialized data to reside at the edge without coupling operational concerns to protocol-level logic. This separation enables infrastructure components such as node monitoring, SLA enforcement, and cluster management to evolve independently of the protocol, while maintaining the security and utility standards required of decentralized data clusters.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The signature of an authorized request proves that the client has sent a request and has a right to access content and t -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.uscis.gov/policy-manual/volume-1-part-b-chapter-2] | [external: https://www.kusari.dev/learning-center/integrity-verification] | [external: https://www.cisa.gov/news-events/news/understanding-digital-signatures] -->

Each authorized request from a client must include metadata and a cryptographic signature. This signature is generated using asymmetric cryptography, combining a hash of the request with the client's private key. The resulting signature proves two things: that the client sent the request, and that the client holds the right to access the requested content. Because the signature is bound to the client's key pair and the specific request payload, it cannot be forged or replayed by an unauthorized party.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The signature construction is signatureBytes = sr25519($requestId$bucketId$timestamp$userPublicKey) -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

Each authenticated client request to a DDC storage node must include a signature that authorizes access to the requested content. The signature is constructed using the sr25519 signing algorithm over a concatenated byte sequence comprising the request identifier, bucket identifier, timestamp, and the user's public key, expressed as signatureBytes = sr25519(requestId + bucketId + timestamp + userPublicKey). This construction ensures that requests cannot be forged, as the signature cryptographically proves both the identity of the client and their right to access the specified bucket at the given point in time.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: DDC tolerates any misbehaviour -->
<!-- SOURCES: [internal: DDC Core Wiki.pdf (66 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

DDC's storage protocol is designed to tolerate a broad range of failure conditions, including both expected and unexpected node shutdowns as well as arbitrary node misbehaviour. Through mechanisms such as erasure coding, client data remains accessible even when one or more nodes leave the network. The protocol enforces a guaranteed level of durability, for example 99.99999%, ensuring that data integrity and availability are maintained across the cluster regardless of individual node failures or malicious activity.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q3 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The mnemonic cannot be recovered from the network if lost -->
<!-- SOURCES: [internal: Get Started with DDC.pdf (9 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The mnemonic generated during account creation is the sole means of recovering access to a DDC wallet. It is never transmitted to or stored on the network, meaning no recovery mechanism exists outside of the phrase itself. If the mnemonic is lost, access to the account and all associated assets is permanently unrecoverable. When creating an account using the CLI command npx @cere-ddc-sdk/cli account --random, the output mnemonic must be recorded and stored securely before proceeding. Anyone who obtains this phrase gains full control of the account.

<!-- EDIT-END: Q3 -->


<!-- EDIT-START: Q1 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The storage protocol tolerates any misbehaviour -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://classic.yarnpkg.com/en/package/@cere-ddc-sdk/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] -->

The DDC storage protocol is designed to tolerate node misbehaviour through its authorization framework, which governs all read and write requests to storage and CDN nodes. Requests must originate from the bucket owner or a party to whom the owner has explicitly granted access, ensuring that unauthorized actors cannot manipulate or corrupt stored data. This access control layer operates across the cluster such that individual node failures or malicious behaviour do not compromise the integrity of the broader system, preserving trustless data transfer guarantees for all participants.

<!-- EDIT-END: Q1 -->


<!-- EDIT-START: Q2 | track: auto | ✅ AUTO-APPLIED -->
<!-- GAP: The protocol accepts plaintext data uploads without rejection -->
<!-- SOURCES: [internal: ADR Authentication and Authorization.pdf (14 pages)] | [external: https://www.cere.network/hub/ddc] | [external: https://www.cere.network/blog/cere-network-s-road-ahead-ecosystem-expansion-cdbe9] | [external: https://www.newsfilecorp.com/release/114279/DeFine-Partners-with-Cere-Network-to-Build-a-Decentralized-and-Secure-NFT-Ecosystem] -->

DDC does not reject plaintext data uploads at the protocol level, but all data intended for restricted access should be encrypted by the client before upload. The protocol enforces access control through short-lived, client-signed credentials rather than through content inspection or rejection. Because leaked credentials are invalid without the originating client signature, the security boundary is maintained at the authentication layer. Access can be granted or revoked at varying levels of granularity, including per-collection or per-piece operations, giving data owners flexible control without relying on the protocol to filter unencrypted content.

<!-- EDIT-END: Q2 -->

---

