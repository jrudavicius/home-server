# Seedbox Product Requirements

Status: Ready for review.

## Purpose

Provide a personal seedbox on the Raspberry Pi Home Server for secure downloading and continued seeding. The owner belongs to several private trackers and needs to manage seeding and ratios while the Pi also runs other services.

This PRD defines the desired product independently of the current Home Server deployment. It covers user needs, expected behavior, scope, and acceptance criteria. Software, providers, deployment architecture, and notification-service selection belong to technical design.

## Goals and priorities

1. **Protect privacy:** all torrent-related internet traffic requires VPN protection. Privacy takes precedence over uninterrupted transfers.
2. **Support private-tracker participation:** keep torrents seeding by default, support explicit tracker policies, and provide useful torrent statistics.
3. **Work with limited supervision:** allow management from home or away, recover automatically from interruptions, and notify the owner when attention is needed.
4. **Coexist with other services:** reduce torrent workload during resource contention and preserve existing files when storage is low.
5. **Keep control with the owner:** manual selection in the first release, deliberate stopping and deletion, and clearly defined policy overrides.

## User and scope

The first release has one administrator: the owner. They use a web interface from a computer or phone to submit and manage torrents, inspect activity, and access completed files. Management and file access must be private and authenticated, both at home and remotely.

Both private trackers and public torrents are supported, with private-tracker requirements a priority. Completed files are available to the owner's personal devices and other Home Server services while remaining available for seeding.

The owner must also be able to save submitted `.torrent` files and retrieve them later for reuse or re-import. These saved metadata files are distinct from the downloaded content and remain available independently of the associated torrent's presence in the active collection.

The Raspberry Pi host, mandatory VPN protection, and computer/phone web access are agreed constraints. Other Home Server services are outside this PRD except for their use of completed files and their need to share resources with the seedbox.

## Intended scale

The first release targets **100 retained torrents and up to two simultaneous downloads**. Retained torrents include those downloading, seeding, or paused under seedbox management.

This is a planning workload to validate against the selected hardware and representative files. It is not a measurement of the current Pi's capacity. Privacy, recovery, and coexistence requirements must hold at this scale.

## Main user journeys

1. **Submit and manage:** the owner chooses a torrent, uploads its `.torrent` file or pastes a magnet link, follows its status, and can pause, resume, or remove it from a computer or phone.
2. **Download and seed securely:** downloading proceeds only with VPN protection. Completed torrents continue seeding by default. Optional tracker policies and explicit per-torrent overrides determine when automatic stopping is allowed.
3. **Use completed files:** the owner retrieves files from home or away, or another Home Server service consumes them, while preserving their availability for seeding.
4. **Respond to a problem:** when protection or storage becomes unavailable, transfers stop safely. The owner receives actionable alerts when attention is needed. Previously running, eligible torrents resume automatically after the prerequisites return.
5. **Save torrent files:** the owner saves a submitted `.torrent` file and can download it again for later reuse or re-import. Removing the associated torrent or its downloaded content does not delete the saved `.torrent` copy.
6. **Remove or recover:** removing a torrent keeps its downloaded content by default. Deleting content or a saved `.torrent` copy is an explicit choice. After a reinstall, the owner can recover the torrent list, settings, saved `.torrent` files, and saved seeding state and resume from surviving content.

## Product requirements

| ID | Requirement |
| --- | --- |
| PRIV-01 | Downloading and seeding must use a VPN so torrent peers do not see the home's internet IP. |
| PRIV-02 | Transfers must stop when protection is unavailable, with no fallback to an unprotected connection. This applies before protection is established and if protection is lost during operation. |
| PRIV-03 | All torrent-related internet traffic must remain protected, including peer connections, tracker communication, and name lookups, during startup, normal operation, and reconnection. |
| PEER-01 | Allow external torrent peers to initiate connections to the seedbox through the VPN. Incoming peer connectivity must work after startup and be restored after VPN reconnection, including changes to the VPN address or assigned peer port, without exposing the home's internet IP. |
| USER-01 | The first release supports one administrator: the owner. |
| TRACK-01 | Support the owner's private trackers and public torrents, keeping tracker-specific policies separate. Compatibility with the owner's selected trackers must be validated before release. |
| TRACK-02 | Honor private-torrent metadata according to [BEP 27](https://www.bittorrent.org/beps/bep_0027.html): announcements and peer discovery must use only the torrent's authorized trackers, with DHT, peer exchange, and local discovery disabled for that torrent. Preserve this isolation during startup, normal operation, restart, and reconnection, including when public torrents are active alongside private torrents. |
| ADD-01 | Accept manually submitted `.torrent` files and magnet links through a web interface usable on a computer and phone. |
| META-01 | Allow the owner to save submitted `.torrent` metadata files and retrieve them later through private, authenticated access for reuse or re-import. Preserve a saved copy until the owner explicitly deletes it, independently of removal of the associated torrent or downloaded content. |
| CONTROL-01 | Show torrent status and provide pause, resume, and removal controls. Deliberate pauses must survive interruptions and restarts. |
| SEED-01 | Completed torrents continue seeding by default until deliberately stopped or an explicitly configured stopping rule applies. Automatic stopping is disabled by default. |
| SEED-02 | Allow optional ratio and seeding-time targets for each tracker. Automatic stopping requires all enabled targets to be met. Explicit per-torrent overrides take precedence over tracker defaults. |
| ACCESS-01 | Allow the owner to manage torrents and retrieve completed files both at home and remotely through private, authenticated access. |
| FILE-01 | Allow completed files to be retrieved by personal devices and used by other Home Server services while preserving the files needed for seeding. |
| FILE-02 | Removing a torrent keeps its downloaded files by default. Deleting its files is a separate, explicit choice that explains the loss of seeding availability and possible effects on other services using those files. |
| RESOURCE-01 | Under resource contention, reduce torrent workload to keep other Home Server services responsive. Torrent throughput yields to those services. |
| SCALE-01 | Support the planning workload of 100 retained torrents and up to two simultaneous downloads while meeting privacy, management, recovery, and coexistence requirements. |
| STORAGE-01 | Pause downloads before they consume a configured free-space reserve. Preserve existing files, disable automatic deletion by default, and continue seeding where possible. Tell the owner when space needs to be freed. |
| RECOVERY-01 | After a VPN outage, restart, or power interruption, resume previously running, eligible torrents within five minutes after VPN protection and required storage are available again. Keep deliberately paused or policy-stopped torrents stopped. Alert the owner if automatic recovery fails. |
| RECOVERY-02 | Make the torrent list, settings, saved `.torrent` files, and saved seeding state recoverable after reinstallation, so activity can resume from surviving content. Downloaded content lost through storage-device failure may be downloaded again; preservation of all downloaded content is outside the first release. |
| STATS-01 | Show each torrent's uploaded and downloaded amounts, torrent ratio, seeding time, and tracker, with grouping or filtering by tracker. The owner checks account-wide ratios on tracker websites in the first release. |
| ALERT-01 | Deliver actionable alerts outside the dashboard when attention is needed, including persistent VPN failure, low storage, tracker problems, and failed automatic recovery. One external delivery channel is sufficient for the first release; its service is selected during technical design. |

## Success and acceptance criteria

The first release succeeds when the owner can complete the main journeys at the intended scale while satisfying the following criteria. These are release acceptance conditions, not claims about an implementation that has already been tested.

| Scenario | Expected outcome |
| --- | --- |
| Normal protected operation | Downloading and seeding work through the VPN; peers see its address rather than the home's internet IP. Torrent-related tracker communication and name lookups are protected as well. |
| Incoming peer connectivity | An external peer can initiate a connection and exchange torrent data through the VPN after startup and after reconnection. Repeat with a changed VPN address or assigned peer port; incoming connectivity is restored and the home's internet IP remains unexposed. |
| Protection unavailable at startup or lost during activity | No torrent-related internet traffic falls back to the unprotected connection. The same condition holds during reconnection. |
| Manual use from computer and phone | The owner can submit a `.torrent` file or magnet link, inspect status, and pause, resume, or remove the torrent. Representative private and public torrents can progress from downloading to seeding. |
| Private-torrent discovery isolation | With private and public torrents active together, verify that private torrents announce and discover peers only through their authorized trackers and do not use DHT, peer exchange, or local discovery. The same isolation holds after restart and VPN reconnection; public torrents can continue using their permitted discovery mechanisms. |
| Saving and retrieving torrent files | The owner can save a submitted `.torrent` file, retrieve a usable copy later, and re-import it. The saved copy remains available after removal of the associated torrent or downloaded content, and is removed only through an explicit choice to delete the saved copy. Access remains private and authenticated. |
| Default seeding and configured policies | Without a stopping rule, completion or reaching a ratio does not automatically stop seeding. When ratio and time targets are both enabled, meeting only one does not trigger stopping. Per-torrent overrides take precedence, and unrelated tracker policies remain unaffected. |
| Home and remote access | The authenticated owner can manage torrents and retrieve files from both locations; unauthenticated access is denied. |
| Use of completed files | Retrieving a file or making it available to another Home Server service preserves its availability for seeding. |
| Removal and deletion | Removing a torrent without explicitly choosing deletion leaves its files intact. Deletion is a separate choice whose effect on seeding and other consumers is explained before it is applied. |
| Storage pressure | Before downloads consume the free-space reserve, they pause and the owner is notified. Existing files remain intact; seeding continues where storage and other prerequisites permit. |
| Routine interruption and recovery | With a mix of running, deliberately paused, and policy-stopped torrents, recovery resumes only previously running, still-eligible torrents within five minutes after protection and required storage return. Failed automatic recovery generates an actionable alert. |
| Reinstallation | The owner can recover the torrent list, settings, saved `.torrent` files, and saved seeding state and resume using surviving content. Recovery of the saved `.torrent` files is required even though recovery of all downloaded content after storage-device failure is outside scope. |
| Intended scale and shared resources | At 100 retained torrents and up to two simultaneous downloads, privacy, management, and recovery checks pass. Under representative competing workloads, torrent workload reduces and other services meet the agreed responsiveness criteria. |
| Statistics and notifications | Torrent statistics are available and can be grouped or filtered by tracker. Problems requiring attention reach the owner outside the dashboard with the affected function and the action needed. |

Resource and storage parameters, representative competing workloads, and measurable responsiveness thresholds must be established during technical design before release validation. The agreed priority for other services remains fixed.

## Outside the first release

- Automatic torrent discovery and submission.
- Integrated tracker-account statistics.
- Multiple seedbox administrators or independent per-user collections.
- Guaranteed recovery of all downloaded content following storage-device failure. Saved `.torrent` files are part of the recoverable seedbox state.
- Defining the rest of the Home Server's services beyond shared-resource and file-use requirements.

## Future features

- **Automatic discovery and downloading:** discover and download torrents from configured feeds. Selection rules and automation behavior will be defined for a future release.
- **Integrated tracker-account statistics:** make account-wide tracker statistics available alongside torrent activity.

## Technical design follow-up

These decisions must satisfy the PRD and are intentionally left to the next phase:

- Select torrent software, a VPN provider supporting incoming peer connectivity, private-access mechanism, deployment architecture, and notification-service integration.
- Choose how to maintain and verify incoming peer connectivity when the VPN address or assigned peer port changes.
- Validate compatibility with the selected private trackers and choose operational values for their configurable policies.
- Size storage, set the free-space reserve and resource budgets, and define representative coexistence benchmarks.
- Choose how to verify VPN protection, preserve and restore saved state, and handle missing or replaced storage.
- Configure notification delivery, persistence thresholds, and repeat behavior.

The current Home Server implementation may inform a later feasibility assessment; it does not define these requirements.

## Terminology

Use the definitions in [the project glossary](../GLOSSARY.md), including the distinction between a torrent ratio and a tracker account ratio.
