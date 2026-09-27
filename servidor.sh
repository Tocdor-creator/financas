#!/data/data/com.termux/files/usr/bin/sh
# Liga/desliga o app em segundo plano no Termux.
# Uso: sh ~/financas/servidor.sh iniciar | parar | status | log
cd "$(dirname "$0")"
PID_FILE=app.pid

rodando() { [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; }

case "$1" in
  iniciar)
    if rodando; then echo "Já está rodando (PID $(cat $PID_FILE))."; exit 0; fi
    termux-wake-lock 2>/dev/null   # impede o Android de pausar o Termux
    setsid nohup python app.py >> app.log 2>&1 < /dev/null &
    echo $! > "$PID_FILE"
    sleep 3
    if rodando; then echo "App iniciado (PID $(cat $PID_FILE))."; else echo "Falhou ao iniciar. Veja: sh servidor.sh log"; exit 1; fi
    ;;
  parar)
    if rodando; then kill "$(cat "$PID_FILE")"; rm -f "$PID_FILE"; echo "App parado."; else echo "Não estava rodando."; fi
    termux-wake-unlock 2>/dev/null
    ;;
  status)
    if rodando; then echo "Rodando (PID $(cat $PID_FILE))."; else echo "Parado."; fi
    ;;
  log)
    tail -n 40 app.log
    ;;
  *)
    echo "Uso: sh servidor.sh iniciar | parar | status | log"; exit 1
    ;;
esac
