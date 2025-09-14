"""
Management command to create a test superuser for admin testing.

This command creates a superuser with predefined credentials for testing
admin functionality in the test suite.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Creates a test superuser for admin testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default='testadmin',
            help='Username for the superuser (default: testadmin)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default='admin@test.com',
            help='Email for the superuser (default: admin@test.com)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='testpass123',
            help='Password for the superuser (default: testpass123)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete existing user if it exists'
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        force = options['force']

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            if force:
                User.objects.filter(username=username).delete()
                self.stdout.write(
                    self.style.WARNING(f'Deleted existing user: {username}')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'User {username} already exists. Use --force to replace.'
                    )
                )
                return

        # Create superuser
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created superuser: {username}\n'
                f'Email: {email}\n'
                f'Password: {password}\n'
                f'Admin URL: /admin/\n'
                f'Use this superuser to test admin functionality.'
            )
        )
