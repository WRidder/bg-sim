# Background tasks

Long jobs run in the background, so you can keep working: **FMU exports** and **CSV downloads** of plotted signals.

The **background tasks** button in the top bar spins with a count while tasks run. A dot shows when a task has finished since you last looked (green when it succeeded, red when it failed). When a task ends, a short notice appears with a **Show** button.

Click the button for the task list. Each task shows its status (Queued, Running, Done, Failed, Cancelled or Refused), its progress and the time it took.

| Button | Does |
| --- | --- |
| **Show details** | reopens the export dialog with the report |
| **Download** | downloads the finished FMU |
| **Cancel** | stops a running task |
| **✕** | removes the task from the list |
| **Clear finished** | removes every finished task |

Closing the export dialog does not stop an export. Recent exports come back in the list after a page reload. Only one FMU export runs at a time; others wait in the queue.
