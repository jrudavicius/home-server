# Home Server

The Home Server hosts several capabilities on a shared Raspberry Pi. This glossary defines the terms agreed during product discovery.

## Language

**Home Server**:
The Raspberry Pi device that hosts the seedbox and other services.
_Avoid_: Seedbox, when referring to the entire device.

**Seedbox**:
The Home Server capability for downloading and seeding files through BitTorrent.
_Avoid_: Home Server, when referring only to this capability.

**Retained torrent**:
A torrent kept under seedbox management, whether downloading, seeding, or paused. Keeping its downloaded content or a saved torrent file after removal does not make it a retained torrent.

**Torrent file**:
A `.torrent` metadata file used to add or re-import a torrent.
_Avoid_: Downloaded content.

**Downloaded content**:
The files transferred by a torrent for the owner to use or seed.
_Avoid_: Torrent file, when referring to downloaded content.

**Owner**:
The person who administers the seedbox, including its torrents and settings. The first version has one owner.

**Seeding policy**:
The owner's rules for when a completed torrent should continue or stop seeding. A policy can apply to a particular tracker.

**Torrent ratio**:
The torrent client's reported upload-to-download ratio for an individual torrent.
_Avoid_: Account ratio.

**Account ratio**:
The account-wide ratio reported by a tracker for the owner's account on that tracker.
_Avoid_: Torrent ratio.
