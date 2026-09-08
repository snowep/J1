from src.agent import Agent


def main():
    agent = Agent()
    print("JARVIS: Commands: create/read/edit/delete/list files, or chat.")
    while (cmd := input("\nYou: ").strip()) and cmd.lower() not in ["exit", "quit"]:
        print(agent.process(cmd))


if __name__ == "__main__":
    main()