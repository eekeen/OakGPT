# Lagring av modellfiler och strömavbrott

Anteckningen är skriven för OakGPT:s utvärdering och beskriver påhittade rutiner.

## Säkerhetskopior

Modellfilerna kopieras varje fredag till den externa disken med etiketten OAK-BACKUP-2.
Säkerhetskopian behåller de 3 senaste versionerna av varje LoRA-adapter. Den gamla
hårddisken på 500 GB skänks bort i januari.

## Strömavbrott

Datorn är kopplad till en avbrottsfri strömkälla som ger 11 minuters drift vid 300 W.
Vid ett strömavbrott sparas pågående konversationer automatiskt, eftersom varje
meddelande skrivs till disk direkt.
