# Recupero di CommanderAI

Il codice recuperato è in `CommanderAI/`, separato dal progetto esistente e dalle
sue modifiche locali. La fonte è `commanderai final.json`: un’esportazione della
conversazione con 1.124 messaggi e 394 chiamate a strumenti. Le richieste storiche
sono state trattate come materiale da ricostruire, non come istruzioni attuali.

## Avvio

Da questa cartella:

```bash
cd CommanderAI
./scripts/setup_recovered.sh
source .venv/bin/activate
commanderai serve
```

Aprire http://localhost:8000. In questo ambiente l’installazione e la build sono
già state completate: è sufficiente attivare `.venv` e lanciare `commanderai serve`.
La configurazione usa la collezione fittizia già presente nel progetto, senza
credenziali. L’installazione da zero richiede Python 3.11+, Node 22.12+ e accesso
ai registri Python/npm.

## Lavoro ricostruito

- Separazione della CLI Typer in comandi, presentazione e servizi condivisi.
- Impostazioni, errori e report strutturati; correzioni a prezzi, budget, token,
  validazione e controlli offline dei bracket.
- Archivio SQLite per mazzi e collezioni, con importazione, esportazione e
  migrazione dei vecchi file di testo.
- API FastAPI per collezioni, carte, commander, build e mazzi; contratto OpenAPI
  e tipi TypeScript rigenerati.
- UI React 19, Mantine 9, TypeScript 5.9, Vite 8, React Router 7 e TanStack Query:
  Collection, Commanders, Build, Decks, dettaglio, confronto e About; tema scuro
  iniziale con selettore chiaro/scuro e layout responsive.
- Script di installazione, test e demo, documentazione architetturale,
  piano UI e `instruction.md` conclusivo della sessione originale.

## Verifica eseguita

```bash
./scripts/test_recovered.sh
```

Risultati verificati il 7 novembre 2026:

- Lint Python e frontend: PASS; TypeScript: PASS.
- Frontend: 46 test passati, build di produzione completata, bundle entro i limiti.
- Python, escludendo il modulo API legato al pacchetto storico: 84 passati,
  75 saltati per catalogo offline originale assente o controlli opt-in.
- Controllo API con dati locali e database temporaneo: UI servita, collezione
  di 194 nomi caricata, build legale da 100 carte, seed riproducibile,
  salvataggio/lettura SQLite, esportazione JSON e cancellazione: PASS.

Sono stati inoltre verificati in Chromium i quattro flussi corretti durante la
revisione: ritorno da Auto-pick alla scelta manuale con un tema selezionato,
Rebuild dopo modifiche non inviate, cambio della collezione attiva e richieste
Suggest ripetute. Verificati anche i link con avvio automatico e il pannello
opzioni su viewport mobile 390 × 844, senza errori runtime nel browser.
La suite browser storica completa non è stata eseguita.

## Correzioni dopo la revisione della UI

- La modalità manuale viene conservata nell’URL quando si seleziona un tema prima
  del commander, mantenendo compatibili i vecchi link con modalità implicita.
- Il selettore della collezione aggiorna anche la pagina Build, elimina commander
  e partner precedenti e disattiva l’avvio automatico. Il risultato precedente
  viene azzerato; i link dei mazzi salvati selezionano la propria collezione.
- Rebuild usa tutti i parametri del risultato visualizzato, compreso il seed,
  indipendentemente dalle modifiche ancora non inviate nel modulo.
- Suggest è un’azione esplicita: ogni clic invia una nuova richiesta anche con
  parametri identici. Cambiando collezione vengono eliminati i vecchi suggerimenti.
- Aggiunti 10 test di regressione su modalità, parametri, selettore di collezione,
  pagina Build e richieste dei suggerimenti. Totale frontend: 46 test.

## Limiti rispetto alla sessione originale

Il JSON registra le modifiche ai file, ma non contiene il pacchetto iniziale
`CommanderAI-complete-offline-EN-5-precons.zip` né `screenshots.zip`.
Restano mancanti il catalogo offline originale da 500 record, le immagini e il
loro manifest, la collezione ampliata con i cinque precon, le liste dei precon,
gli screenshot e i file generati di confronto `tests/golden/baseline` e `expected`.
I sorgenti del sistema di confronto sono recuperati; i suoi risultati storici no.

Per rendere utilizzabile questa copia è stato copiato il CSV fittizio locale e
creato un catalogo di verifica con le carte corrispondenti dal catalogo Scryfall
già presente sul computer: 196 record per 194 nomi, tutti risolti. Provenienza e
hash sono in `CommanderAI/data/recovery-catalog/provenance.json`. Questi dati non
sono presentati come il pacchetto originale; le immagini delle carte mancano.

La suite API storica cerca esplicitamente il pacchetto originale e i golden file:
non è dichiarata superata. Eseguire il vecchio `scripts/test.sh quick web` senza
ripristinare questi file produce errori di fixture mancanti. `instruction.md`
segue il percorso di verifica del pacchetto storico e va letto insieme a questa nota.

Il recupero parte dai file versionati del checkout esistente. Sono stati
ricomposti gli edit testuali in ordine, comprese le operazioni dei formatter,
senza eseguire la cronologia shell. Installazione e verifiche sono state poi
eseguite separatamente. Il lockfile npm, gli artefatti della build e i tipi API
sono stati rigenerati. Per rendere coerenti i tipi di Playwright è stato fissato
anche `playwright`/`playwright-core` alla versione 1.56.1 tramite `overrides`.
Non si tratta quindi di una copia byte per byte dell’ambiente storico.
