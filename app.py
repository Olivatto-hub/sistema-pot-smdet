ModuleNotFoundError: This app has encountered an error. The original error message is redacted to prevent data leaks. Full error details have been recorded in the logs (if you're on Streamlit Cloud, click on 'Manage app' in the lower right of your app).
Traceback:

File "/mount/src/sistema-pot-smdet/app.py", line 524, in <module>
    main()
    ~~~~^^
File "/mount/src/sistema-pot-smdet/app.py", line 517, in main
    dashboard_screen()
    ~~~~~~~~~~~~~~~~^^
File "/mount/src/sistema-pot-smdet/app.py", line 421, in dashboard_screen
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
         ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.13/site-packages/pandas/io/excel/_xlsxwriter.py", line 197, in __init__
    from xlsxwriter import Workbook
