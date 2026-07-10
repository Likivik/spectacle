

[likivik@traversal:/Storage/Git/spectacle]$ ssh-keygen -t ed25519 -f ~/.ssh/vps_ed25519 -N ""
Generating public/private ed25519 key pair.
Your identification has been saved in /home/likivik/.ssh/vps_ed25519
Your public key has been saved in /home/likivik/.ssh/vps_ed25519.pub
The key fingerprint is:
SHA256:006aIZBLBW3T0vK29dZVPuSKwXGjtXFFWI04LxZl8nI likivik@traversal
The key's randomart image is:
+--[ED25519 256]--+
|    .o.o    .oo=*|
|     o* o  .+Oooo|
|    +. =  . *+E..|
|   . o  o..+o+.oo|
|    . ..Sooooo...|
|       ..B .o..  |
|        o ..     |
|                 |
|                 |
+----[SHA256]-----+

[likivik@traversal:/Storage/Git/spectacle]$ ssh-copy-id -i ~/.ssh/vps_ed25519 root@148.253.214.185
/run/current-system/sw/bin/ssh-copy-id: INFO: Source of key(s) to be installed: "/home/likivik/.ssh/vps_ed25519.pub"
The authenticity of host '148.253.214.185 (148.253.214.185)' can't be established.
ED25519 key fingerprint is: SHA256:3IgJNEtdGYAjdIRj5Ad8tCgS5eRdsmVDd9ORfzRr0Qg
This key is not known by any other names.
Are you sure you want to continue connecting (yes/no/[fingerprint])? y
Please type 'yes', 'no' or the fingerprint: yes
/run/current-system/sw/bin/ssh-copy-id: INFO: attempting to log in with the new key(s), to filter out any that are already installed
/run/current-system/sw/bin/ssh-copy-id: INFO: 1 key(s) remain to be installed -- if you are prompted now it is to install the new keys
root@148.253.214.185's password:

Number of key(s) added: 1

Now try logging into the machine, with: "ssh -i /home/likivik/.ssh/vps_ed25519 'root@148.253.214.185'"
and check to make sure that only the key(s) you wanted were added.


---
So far manually had to paste Root password and IP
---


[likivik@traversal:/Storage/Git/spectacle]$ ssh root@148.253.214.185 lsblk
NAME    MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
sr0      11:0    1  7.4M  0 rom
vda     253:0    0   75G  0 disk
├─vda1  253:1    0 73.9G  0 part /
├─vda13 253:13   0 1023M  0 part /boot
├─vda14 253:14   0    4M  0 part
└─vda15 253:15   0  106M  0 part /boot/efi

---
disko template for VPS uses vda as default so no changes needed
---









