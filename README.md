# BikeAble

BikeAble shows cyclists in Skopje a map of road conditions and hazards. You can report a problem
with a photo, AI describes what's in the photo, and you can compare routes to pick the most
comfortable one. It's a hackathon prototype for "Fix My City"; demo reports are labelled as
synthetic.

## Screenshots from the app
![Alternative description text](https://i.imgur.com/NeEHIs4.png)
![Alternative description text](https://i.imgur.com/sGziy1s.png)
![Alternative description text](https://i.imgur.com/bN3NRlp.png)
![Alternative description text](https://i.imgur.com/eg5krjt.png)
![Alternative description text](https://i.imgur.com/iEyFkGV.png)
![Alternative description text](https://i.imgur.com/koXEqXI.png)
![Alternative description text](https://i.imgur.com/5bYY0Rl.png)
![Alternative description text](https://i.imgur.com/vyOiDTb.png)
![Alternative description text](https://i.imgur.com/UEBpLcC.png)


## What you need

- Linux or macOS
- git
- Python 3.12
- make

## Run it

1. Download the code:

   ```bash
   git clone https://github.com/diischm/hacktoberfest2026.git
   ```

2. Go into the folder:

   ```bash
   cd hacktoberfest2026
   ```

3. Install everything (takes a minute or two):

   ```bash
   make install
   ```

4. Create your settings file:

   ```bash
   cp .env.example .env
   ```

5. Set up the database:

   ```bash
   make migrate
   ```

6. Add the demo reports:

   ```bash
   make loaddemo
   ```

7. Start the app:

   ```bash
   make run
   ```

8. Open <http://localhost:8000> in your browser.

## AI photo analysis (optional)

The app works without any key: photos get a sample AI answer. To use the real AI:

1. Get a free Gemini API key at [Google AI Studio](https://aistudio.google.com) ("Get API key").
2. Open the `.env` file and set:

   ```
   AI_MODE=live
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-3.8-flash
   ```

3. Check it works (this sends the photo to Google once):

   ```bash
   make ai-smoke IMG=path/to/photo.jpg
   ```

4. Stop the app (Ctrl+C) and start it again with `make run`.

Optional: answers are faster with `GEMINI_THINKING_LEVEL=low` in `.env` (Gemini 3 models only;
leave it empty for other models). Run `make ai-smoke` again after changing it.

Never share or commit the `.env` file: it holds your key.

On the free tier Google may use the photos you send to improve its products, so don't upload
photos where people can be recognised.

## Open it on your phone

1. Connect the phone to the same Wi-Fi as the laptop.
2. Find the laptop's IP address.

   On Linux (the first number shown):

   ```bash
   hostname -I
   ```

   On macOS:

   ```bash
   ipconfig getifaddr en0
   ```

3. In `.env`, put that IP after `DJANGO_ALLOWED_HOSTS=`, for example `DJANGO_ALLOWED_HOSTS=192.168.1.23`.
4. Stop the app (Ctrl+C) and start it again:

   ```bash
   make run
   ```

5. On the phone, open `http://<IP>:8000`, for example `http://192.168.1.23:8000`.

## Admin (verify or resolve reports)

1. Create an admin login (it asks for a username, email and password):

   ```bash
   make superuser
   ```

2. With the app running, open <http://localhost:8000/admin> and log in.

## Stop / update

- To stop the app, press Ctrl+C in the terminal where it runs.
- After getting new code (`git pull`), run these again before `make run`:

  ```bash
  make install
  ```

  ```bash
  make migrate
  ```

## Problems?

- **"No module named ..."**: run `make install` again.
- **"DisallowedHost" or "Bad Request (400)" on the phone**: add the laptop's IP to
  `DJANGO_ALLOWED_HOSTS` in `.env`, then restart `make run`.
- **"That port is already in use"**: another copy of the app is running. Stop it with Ctrl+C
  in its terminal, or close that terminal.
- **The map is empty**: run `make loaddemo`.

Developers: see [CONTRIBUTING.md](CONTRIBUTING.md).
