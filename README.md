# Documentatie Server CoAP- Remote Storage

__1. Introducere__


Scopul acestui proiect este implementarea unui server CoAP (Constrained Application Protocol) care permite stocarea și gestionarea fișierelor trimise de un client într-o arhitectură de tip remote storage.  
Protocolul CoAP este conceput pentru sisteme cu resurse limitate (dispozitive IoT, senzori, microcontrolere), fiind o alternativă ușoară la HTTP, bazată pe UDP.
Serverul implementat oferă o serie de funcționalități:  
&nbsp;&nbsp;&nbsp;&nbsp;	-încărcarea și descărcarea fișierelor  
&nbsp;&nbsp;&nbsp;&nbsp;	-crearea și ștergerea fișierelor  
&nbsp;&nbsp;&nbsp;&nbsp;	-navigarea în structura de directoare  
&nbsp;&nbsp;&nbsp;&nbsp;	-mutarea fișierelor între directoare  
Comunicarea între client și server se face exclusiv prin mesaje CoAP, transmise prin socket-uri UDP.  

<br>

__2.Formatul pachetelor__ [1]

Un pachet CoAP reprezintă unitatea de bază de comunicare între client și server. Fiecare pachet conține informațiile necesare pentru identificarea, procesarea și livrarea corectă a mesajului. Structura unui pachet CoAP este alcătuită din mai multe câmpuri, fiecare având un rol bine definit.

<br>

Structura pachetelor este următoarea: 
```
    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |Ver| T |  TKL  |      Code     |          Message ID           |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |   Token (if any, TKL bytes) ...
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |   Options (if any) ...
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |1 1 1 1 1 1 1 1|   { "cheie": "data", "cheie": "data", ... }
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

<br>

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-Header:  are o lungime fixă de 4 octeți și este poziționat la începutul fiecărui pachet. Acesta conține informații generale despre mesaj, cum ar fi versiunea protocolului, tipul mesajului( Confirmable (0), Non-confirmable (1), Acknowledgement (2),    Reset (3)), codul metodei (GET, POST, etc.) și un identificator unic de mesaj (Message ID).   

<br>

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-Token; asigură corelarea cererilor cu răspunsurile. Clientul generează o cerere către server, incluzând un token unic care se va regăsi în răspunsul trimis. Utilizarea acestuia este opțională.  

<br>

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-Options: conțin informații suplimentare despre mesaj, cum ar fi tipul de conținut, calea resursei, dimensiunea datelor sau parametri specifici aplicației.   
În cadrul proiectului, vom specifica tipul formatului de payload ( este acceptat doar json) și tipul de fișier cerut (file, director) , dacă este cazul.   

<br>

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-Payload; reprezintă datele transmise între client și server. Poate conține, de exemplu, conținutul unui fișier, structura unui director sau un mesaj de confirmare.   
Dimensiunea maximă recomandată pentru un pachet CoAP este de aproximativ 1152 octeți.Din acest total, payloadul poate ocupa de regulă până la 1024 octeți.  
În cadrul acestui proiect ne vom limita la dimensiunea maximă unui pachet UDP, deci 64 de kilobytes.  
Dacă mesajul depășește această limită, conținutul trebuie împărțit în mai multe pachete. Fragmentarea se realizează la nivelul aplicației, iar fiecare pachet trebuie identificat astfel încât receptorul să poată reconstrui corect mesajul complet.  
În cadrul proiectului, payloadul este sub format de json, serverul/clientul va accepta doar tipuri specifice de jsonuri, specificate în secțiunea (3).

<br>

Tipuri de mesaje: [2]   

Protocolul CoAP definește patru tipuri principale de mesaje, indicate în câmpul Type din Header. Acestea stabilesc modul de confirmare și comportamentul comunicării între client și server:   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-CON (Confirmable) – mesaj confirmabil care necesită primirea unui răspuns de tip ACK. Dacă răspunsul nu este primit într-un anumit interval de timp, mesajul este retransmis.   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-NON (Non-confirmable) – nu necesită răspuns de tip ACK; este folosit pentru transmisii rapide, unde pierderea ocazională de pachete este acceptabilă.   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-ACK (Acknowledgement) – mesaj de confirmare trimis ca răspuns la un mesaj CON, pentru a semnala primirea acestuia.  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-RST (Reset) – mesaj de resetare, transmis atunci când un nod primește un pachet pe care nu îl recunoaște sau nu îl poate procesa.   

<br>

Metode de cerere: [3] [6]   


Protocolul CoAP folosește un set de metode similare cu cele din HTTP, care definesc acțiunile efectuate asupra resurselor de pe server:   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-GET(cod 0.01): solicită accesul la o resursă de pe server și returnează conținutul acesteia. Ca urmare,răspunsul trebuie să conțină codul 2.05 (Content) pentru a transmite conținutul fișierului sau al directorului solicitat de client.   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-POST(cod 0.02): trimite date către server pentru a crea sau actualiza o resursă. În cazul unei cereri POST, răspunsul trebuie să conțină codul 2.01 (Created) dacă fișierul a fost încărcat cu succes pe server sau codul 2.05 (Content) dacă se returnează o confirmare cu metadatele fișierului.   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-PUT(cod 0.03): înlocuiește complet conținutul unei resurse existente (opțional, în funcție de implementare). În cazul unei astfel de cereri,răspunsul trebuie să conțină codul 2.04 (Changed) pentru a confirma că fișierul existent a fost suprascris cu succes.   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-DELETE(cod 0.04):  șterge o resursă de pe server.În cazul unei cereri DELETE, răspunsul trebuie să conțină codul 2.02 (Deleted) pentru a confirma că fișierul sau directorul a fost șters cu succes de pe server.   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-În contextul proiectului, va fi definită și o metodă suplimentară mai precis metoda MOVE(cod 0.05), care va fi utilizată pentru mutarea unui fișier anume într-un alt director *existent*, iar răspunsul corespunzător unei astfel de cereri ar avea codul 2.04 (Changed).    

<br>

Tipuri de răspunsuri: [4] [7]   


Răspunsurile CoAP sunt mesaje trimise de server către client pentru a indica rezultatul unei cereri. Ele folosesc câmpul Code din antet pentru a comunica dacă cererea a fost procesată cu succes sau dacă a apărut o eroare.   
 În aplicația de tip remote storage, răspunsurile confirmă operațiile efectuate asupra fișierelor și directoarelor, precum descărcarea, încărcarea, ștergerea sau mutarea acestora:   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-2.05 (Content) este folosit pentru a transmite conținutul fișierelor sau al directoarelor. În cazul unei cereri GET, acest cod indică faptul că datele returnate sunt valide și actuale.   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-2.03 (Valid) indică faptul că resursa nu s-a modificat de la ultima interogare.  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-2.01 (Created) confirmă că o resursă a fost creată cu succes pe server.  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-2.04 (Changed) confirmă că resursa existentă a fost modificată.  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-2.02 (Deleted) confirmă ștergerea unei resurse de pe server.  

<br>

Mecanismul Piggybacked Response: [5] 


În cazul mesajelor Confirmable, serverul poate trimite răspunsul în două moduri:   
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-Piggybacked Response presupune trimiterea directă a răspunsului  în același pachet cu mesajul de confirmare (ACK).  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;-Separate Response determină faptul că serverul trimite mai întâi un mesaj ACK pentru confirmarea cererii și apoi, într-un pachet separat se trimite răspunsul efectiv.  

<br>

Pachete proprietare (pentru aplicație)  



| Tip      | Descriere     | Conținut Payload       |
| :---     |     :----:    | :---                   |
|FILE_UPLOAD | Client → Server | Header CoAP (POST) + nume fișier + conținut fișier |
|FILE_DOWNLOAD | Client → Server | Header CoAP (GET) + calea fișierului |
|FILE_DELETE | Client → Server | Header CoAP (DELETE) + calea fișierului |
|FILE_MOVE | Client → Server | Header CoAP (MOVE) + calea sursă + calea destinație |
|DIR_LIST | Client → Server |Header CoAP (GET) + calea directorului |
|RESPONSE_OK / ERROR | Server → Client | Header CoAP (ACK) + cod + mesaj textual |

<br><br>
__3.Interacțiunile client–server__

<br>

-Upload fișier (POST /upload)   
&nbsp;&nbsp;&nbsp;&nbsp;Client trimite pachet Confirmable cu cod 0.02 (POST)   
&nbsp;&nbsp;&nbsp;&nbsp;Server salvează fișierul → trimite ACK 2.01 Created  
&nbsp;&nbsp;&nbsp;&nbsp;Payload: [path] + [file content]   

client:   
```
{
  "path": "/directory/file.txt",
  "content": "Data"
}
```
Server:
```
{
  "status": "created",
  "path": "/directory/file.txt",
  "size": 1024
}
{
  "status": "error",
  "message": "Unable to execute"
}
```

<br>

-Download fișier (GET /download)   
&nbsp;&nbsp;&nbsp;&nbsp;Client trimite GET cu calea fișierului   
&nbsp;&nbsp;&nbsp;&nbsp;Server trimite ACK 2.05 Content + payload cu fișierul  

Client:  
```
{
  "path": "/directory/file.txt"
}
```
server:
```
{
  "name": "file.txt",
  "size": 2048,
  "content": "Data"
}

{
  "status": "error",
  "message": "Unable to execute"
}
```

<br>

-Ștergere fișier (DELETE /path)  
&nbsp;&nbsp;&nbsp;&nbsp;Client → Confirmable cod 0.04 (DELETE)  
&nbsp;&nbsp;&nbsp;&nbsp;Server → ACK 2.02 Deleted  

Client:  
```
{
  "path": "/directory/file.txt"
}
```
Server:
```
{
  "status": "deleted",
  "path": "/directory/file.txt"
}
{
  "status": "error",
  "message": "Unable to execute"
}
```

<br>

-Mutare fișier (MOVE /src /dst)   
&nbsp;&nbsp;&nbsp;&nbsp;Client → Confirmable cod 0.08 (MOVE)  
&nbsp;&nbsp;&nbsp;&nbsp;Server → ACK 2.01 Created dacă mutarea a reușit  

client:  
```
{
  "source": "/directory/file_1.txt",
  "destination": "/directory2/file_1.txt"
}
```
server:  
```
{
  "status": "moved",
  "from": "/directory/file_1.txt",
  "to": "/directory2/file_1.txt"
}
{
  "status": "error",
  "message": "Unable to execute"
}
```

<br>

-Listare directoare (GET /list)  
&nbsp;&nbsp;&nbsp;&nbsp;Client → GET pe director  
&nbsp;&nbsp;&nbsp;&nbsp;Server → 2.05 Content cu payload (nume fișiere/directoare)  

client:  
```
{
  "name": "directory",
  "type": "directory",
  "items": ["file.txt", "file.pdf", "directory2/"]
}
```
Server:  
```
{
  "path": "/directory/"
}
{
  "status": "error",
  "message": "Unable to execute"
}
```

<br><br>

__4. Threading și paralelizare__


| Fir | Responsabilitate | Detalii|
| :--- | :----: | :----: |
| Thread Main |Ascultă pachete UDP | Socket.recvfrom()  într-un loop infinit|
|Thread de procesare cereri | Decodifică pachetul și identifică metoda | Creează un task pentru fiecare cerere nouă |
|Thread pentru fișiere | Operații I/O (citire/scriere/mutare) | Evită blocarea firului principal |
|Thread de răspuns | Trimite pachetele ACK/Response | Confirmă cererea, trimite payload-ul |

<br><br>

__5. Schelet logic__


```
Main Thread
|
|
—> Ascultă socketul UDP
—>Pentru o cerere primită:
|             |
|             —> Thread de Procesare Cereri 
|                              |  
|                              —> Decodifică pachetul
|                              —> Identifică metoda 
|                              —> Dacă e nevoie crează:
|                               |        |
|                               |        —> Thread pentru fișiere (doar dacă e necesar)
|                               |	        	   |
|                               |                  —> Execută operații pe fișiere sau directoare
|	                    |	               |
|                               |                 ∨
|                               ——> Thread de răspuns
|                                                  |
|                                                  —> Formează mesajul de răspuns și îl trimite
|
—> Se așteaptă alte cereri
```
<br><br>

[1] https://datatracker.ietf.org/doc/html/rfc7252#section-3  
[2] https://datatracker.ietf.org/doc/html/rfc7252#section-4  
[3] https://datatracker.ietf.org/doc/html/rfc7252#section-5.1   
[4] https://datatracker.ietf.org/doc/html/rfc7252#section-5.2   
[5] https://datatracker.ietf.org/doc/html/rfc7252#section-5.2.1   
[6] https://datatracker.ietf.org/doc/html/rfc7252#section-5.8  
[7] https://datatracker.ietf.org/doc/html/rfc7252#section-5.9     

<br>
