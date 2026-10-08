import json
import os

# 数据保存的文件名
DATA_FILE = "todo_list.json"

def load_tasks():
    """从 JSON 文件加载任务列表，如果文件不存在则返回空列表"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_tasks(tasks):
    """将任务列表保存到 JSON 文件"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=4)

def show_tasks(tasks):
    """显示所有任务"""
    if not tasks:
        print("\n📭 当前没有待办事项。")
        return
    print("\n📋 待办事项列表：")
    for i, task in enumerate(tasks, start=1):
        status = "✅" if task["done"] else "⬜"
        print(f"{i}. {status} {task['title']}")

def add_task(tasks):
    """添加新任务"""
    title = input("请输入任务内容：").strip()
    if title:
        tasks.append({"title": title, "done": False})
        save_tasks(tasks)
        print(f"✅ 已添加任务：{title}")
    else:
        print("⚠️ 任务内容不能为空。")

def mark_done(tasks):
    """标记任务为已完成"""
    show_tasks(tasks)
    if not tasks:
        return
    try:
        num = int(input("请输入要标记完成的任务编号："))
        if 1 <= num <= len(tasks):
            tasks[num - 1]["done"] = True
            save_tasks(tasks)
            print(f"🎉 任务「{tasks[num - 1]['title']}」已完成！")
        else:
            print("⚠️ 编号超出范围。")
    except ValueError:
        print("⚠️ 请输入有效的数字。")

def delete_task(tasks):
    """删除任务"""
    show_tasks(tasks)
    if not tasks:
        return
    try:
        num = int(input("请输入要删除的任务编号："))
        if 1 <= num <= len(tasks):
            removed = tasks.pop(num - 1)
            save_tasks(tasks)
            print(f"🗑️ 已删除任务：{removed['title']}")
        else:
            print("⚠️ 编号超出范围。")
    except ValueError:
        print("⚠️ 请输入有效的数字。")

def main():
    tasks = load_tasks()
    while True:
        print("\n===== 待办事项管理 =====")
        print("1. 查看任务")
        print("2. 添加任务")
        print("3. 标记完成")
        print("4. 删除任务")
        print("5. 退出")
        choice = input("请选择操作（1-5）：").strip()

        if choice == "1":
            show_tasks(tasks)
        elif choice == "2":
            add_task(tasks)
        elif choice == "3":
            mark_done(tasks)
        elif choice == "4":
            delete_task(tasks)
        elif choice == "5":
            print("👋 再见！")
            break
        else:
            print("⚠️ 无效选择，请重新输入。")

if __name__ == "__main__":
    main()
