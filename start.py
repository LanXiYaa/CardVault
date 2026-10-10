import sys

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--hash-worker':
        from cardvault.hash_worker import main
        raise SystemExit(main())
    from cardvault.gui import main
    main()
