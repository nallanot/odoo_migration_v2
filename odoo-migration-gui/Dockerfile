FROM docker:cli

RUN apk add --no-cache python3 git
WORKDIR /app
COPY migration.py native_policy.py oneshot.py ai_agent.py remote_worker.py interface.html ./
COPY skills /app/skills

EXPOSE 8765
ENTRYPOINT ["python3", "/app/migration.py"]
CMD ["--bind", "0.0.0.0", "--workdir", "/opt/odoo-migration"]
