from nicegui import ui, app
from datetime import datetime
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# --- SUPABASE CONFIGURATION ---
from supabase import create_client, Client

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class AppState:
    def __init__(self):
        self.email = ""
        self.user_email = ""
        self.is_logged_in = False
        self.otp_sent = False
        self.otp_timer = 0  # Added for Patient Portal matching timer logic
        self.current_page = "dashboard"
        self.member_view = "list"    
        self.bill_type = None
        self.left_drawer_open = True
        
        # --- AUTOMATIC CURRENT MONTH DECIDE LOGIC (6 Tarik Rule) ---
        today = datetime.now()
        if today.day <= 5:
            prev_month_idx = today.month - 1 if today.month > 1 else 12
            calc_month = datetime(today.year, prev_month_idx, 1).strftime('%B')
        else:
            calc_month = today.strftime('%B')
            
        self.selected_month = calc_month  
        self.dynamic_family_members = [] 
        self.existing_head_id = None  
        self.billing_tab = "current"  
        self.history_month = calc_month  

        # --- STATES FOR BILL LOCK & STATUS BAR ---
        self.is_submitted = False  
        self.bill_status = "Pending at Renter"  
        self.submitted_kwh = ""
        
        # Active Renter ID (UUID) simulation
        self.active_renter_head_id = None
        self.locked_head_id = None
        self.renter_id = None
        self.room_no = None
        self.rent_tab = "current"
        self.pay_month = None
        self.qr_token = None
        self.qr_mode = False

@ui.page('/')
def main_page():
    state = AppState()
    try:
        token = ui.context.client.request.query_params.get(
            'token'
        )

        if token:
            state.qr_token = token
            state.qr_mode = True

    except:
        pass
    # Persistent check
    if app.storage.user.get('is_logged_in'):
        saved_email = app.storage.user.get('user_email')
        renter = supabase.table(  'renters' ).select( 'status' ).eq(  'email',  saved_email ).limit(1).execute()
        if renter.data:
            status = str(  renter.data[0].get('status', '') ).upper()
            if status in ['ACTIVE', 'LIVING']:
                state.is_logged_in = True
                state.user_email = saved_email
            else:
                app.storage.user.clear()
        else:
            app.storage.user.clear()

    ui.query('body').style('background-color: #f1f8e9; margin: 0; padding: 0;')

    ui.add_head_html('''
    <style>
        /* Mobile par drawer 100% width na le, balki sirf 200px rahe */
        @media (max-width: 768px) {
            .q-drawer { width: 200px !important; } 
        }
        @keyframes blinker {
            50% { opacity: 0; }
        }
        .blink-text {
            animation: blinker 1s linear infinite;
            color: red;
            font-weight: bold;
        }
        .responsive-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
        @media (max-width: 600px) {
            .responsive-grid {
                grid-template-columns: 1fr; /* Mobile par sirf 1 column */
            }
        }
    </style>
''')
    
    

    # --- PATIENT PORTAL CORE LOGIN FUNCTIONS (INTEGRATED) ---
    def handle_send_otp(email_val):
        if not email_val:
            ui.notify('Email Not Found', type='warning')
            return
            
        email_clean = str(email_val).strip() # Trailing space hatane ke liye
        
        if state.otp_sent and state.otp_timer > 0:
            ui.notify(f'Please wait {state.otp_timer}s', type='warning')
            return
        if "@" not in email_clean:
            ui.notify('Email Not Found', type='warning')
            return
            
        try:
            # FIX: Sabhi records check karne ke liye lowercase matching engine switch kiya hai
            renter_res = supabase.table('renters').select('id,email,status').execute()
            
            matched_renter = None
            if renter_res.data:
                for r in renter_res.data:
                    if str(r.get('email', '')).strip().lower() == email_clean.lower():
                        matched_renter = r
                        break
                        
            if not matched_renter:
                ui.notify('Email Not Found ', type='negative')
                return
            status = str(  matched_renter.get('status', '')).upper()
            if status not in ['ACTIVE', 'LIVING']:
                ui.notify(   'Contact Admin',  type='negative' )
                return
     
            # Database me jaisa email save hai exact wahi exact format string authentication me pass karein
            final_email = matched_renter['email']
            supabase.auth.sign_in_with_otp({"email": final_email})
            
            state.email = final_email
            state.otp_sent = True
            state.otp_timer = 60
            ui.notify(f'OTP sent to {final_email}', type='positive')
            sidebar_content.refresh()
           # main_content.refresh()
        except Exception as e:
            ui.notify(f'Error: {str(e)}', type='negative')
    def qr_auto_login():
        if not state.qr_token:
            return
        try:
            # Step 1 : QR token se room nikalo
            room_lookup = supabase.table( 'renters' ).select( 'room_no' ).eq( 'qr_token',  state.qr_token ).limit(1).execute()
            if not room_lookup.data:
                ui.notify('Invalid QR')
                return
            room_no = room_lookup.data[0]['room_no']
            # Step 2 : Us room ka ACTIVE/LIVING renter nikalo
            renters = supabase.table(  'renters' ).select(  'email,status').eq( 'room_no',  room_no ).execute()
            active_renter = None
            for r in renters.data:
                status = str(  r.get('status', '') ).upper()
                if status in ['ACTIVE', 'LIVING']:
                    active_renter = r
                    break
            if not active_renter:
                ui.notify('Room Not Active')
                return
            email = active_renter['email']
            handle_send_otp(email)
        except Exception as ex:
            print(ex)
        
    def handle_verify_otp(otp_val):
        try:
            res = supabase.auth.verify_otp({"email": state.email, "token": otp_val.strip(), "type": "email"})
            # Verification re-check
            if not res.user:
                ui.notify('Invalid OTP', type='negative')
                return

            app.storage.user['user_email'] = state.email
            app.storage.user['is_logged_in'] = True
            state.user_email = state.email
            state.is_logged_in = True
            state.otp_sent = False
            state.otp_timer = 0
            state.current_page = "dashboard"
            
            # DIRECT STATE SYNC ENGINE (Pre-loading complete tuple before refresh)
            renter_lookup = supabase.table('renters').select('*').execute()
            if renter_lookup.data:
                for r in renter_lookup.data:
                    if str(r.get('email', '')).strip().lower() == state.user_email.lower():
                        state.renter_id = r['id']
                        state.room_no = r['room_no']
                        state.active_renter_head_id = r['head_member_id']
                        break

            ui.notify('Logged in successfully!', type='positive')
            sidebar_content.refresh()
            main_content.refresh()
        except Exception as e:
            ui.notify('Session expired or Invalid OTP', type='negative')

    def logout():
        app.storage.user.clear()
        state.is_logged_in = False
        state.otp_sent = False
        state.otp_timer = 0
        state.user_email = ""
        state.email = ""
        state.renter_id = None
        state.room_no = None
        state.active_renter_head_id = None
        state.current_page = "dashboard"
        ui.notify('Logged out')
        sidebar_content.refresh()
        main_content.refresh()

    def countdown_tick():
        if state.otp_timer > 0: 
            state.otp_timer -= 1

    ui.timer(1.0, countdown_tick)

    def open_page(label):
        if label == 'Member Detail': 
            state.current_page = 'profile'
            state.member_view = 'list'
        elif label == 'Electric Bill': 
            state.bill_type = 'Electric'
            state.current_page = 'billing'
            state.billing_tab = 'current'
        elif label == 'Gas Bill': 
            state.bill_type = 'Gas'
            state.current_page = 'billing'
            state.billing_tab = 'current'
        elif label == 'Rent Ledger':
            state.bill_type = 'Rent'
            state.current_page = 'renting'
            state.rent_tab = 'current'
        elif label == 'Pay Now':
             state.current_page = 'payment'
        main_content.refresh()

    with ui.header().classes(' row items-center shadow-sm no-wrap').style('background-color: #2e7d32; height: 48px;'):
        # Menu button jo drawer toggle karega
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=white dense')
        ui.label(' Meena Residency ').classes('text-white text-mg font-bold ml-2 no-wrap')
    @ui.refreshable
    def render_notices():
        try:
            res = (
                supabase.table('hub_users')
                .select('notice')
                .eq('id', 1)
                .single()
                .execute() )
            notice_text = (
                res.data.get('notice', '')
                if res.data else '' )
            if not notice_text:
                ui.label( 'No active notice' ).classes(  'text-xs text-gray-600' )
                return
            items = [
                x.strip()
                for x in str(notice_text).split(',')
                if x.strip()]
            with ui.column().classes('w-full gap-1'):
                for idx, item in enumerate(items, 1):
                    # Agar DB me 1-,2-,3- likha hai to hata do
                    if '-' in item:
                        left, right = item.split('-', 1)
                        if left.strip().isdigit():
                            item = right.strip()
                    with ui.grid(columns='auto 1fr').classes('w-full gap-x-2'):
                        ui.label(  f'{idx}.').classes( 'font-bold text-xs text-green-800')
                        ui.label(  item).classes( 'text-xs text-blue-700 font-bold').style( 'word-break:break-word;')
        except Exception as e:
            print(f'Notice Error: {e}')
            ui.label(  'Error loading notice'  ).classes('text-xs text-red-500' )        
    
    
    

 
 
    drawer = ui.left_drawer(value=True).props('width=200').style('background-color: #ffffff; border-right: 1px solid #c8e6c9;')
    with drawer:
        @ui.refreshable
        def sidebar_content():
            if not state.is_logged_in:
                ui.label('Renter Login').classes('text-2xl font-bold text-green-900 mt-4 ml-2')
                if state.qr_mode and not state.otp_sent:
                    qr_auto_login()
                with ui.card().classes('m-2 p-4 shadow-lg'):
                    with ui.column().bind_visibility_from(state, 'otp_sent', backward=lambda x: not x).classes('w-full'):
                        if not state.qr_mode:

                            e_input = ui.input(
                                label='Registered Email'
                            ).classes('w-full')

                            ui.button(
                                'Get OTP',
                                on_click=lambda: handle_send_otp(e_input.value)
                            ).classes(
                                'w-full mt-1 bg-green-700 text-white'
                            )

                        else:

                            ui.label(
                                'Room Verified'
                            ).classes(
                                'text-green-700 font-bold'
                            )

                            ui.label(
                                'OTP Sent Automatically'
                            ).classes(
                                'text-blue-700 text-xs'
                            )
                    with ui.column().bind_visibility_from(state, 'otp_sent').classes('w-full'):
                        ui.label().bind_text_from(state, 'email', backward=lambda x: f'OTP sent to {x}').classes('text-[10px] text-gray-500')
                        o_input = ui.input(label='Enter OTP').classes('w-full').props('dense autofocus').on('keydown.enter', lambda: handle_verify_otp(o_input.value))
                        ui.button('Verify OTP', on_click=lambda: handle_verify_otp(o_input.value)).classes('w-full mt-2 bg-blue-700 text-white')
                        ui.label().bind_text_from(state, 'otp_timer', backward=lambda t: f'Resend in {t}s' if t > 0 else '').classes('text-xs text-gray-500').bind_visibility_from(state, 'otp_timer', backward=lambda t: t > 0)
                        ui.button('Resend OTP', on_click=lambda: handle_send_otp(state.email)).props('flat dense').classes('text-orange-600 text-xs').bind_visibility_from(state, 'otp_timer', backward=lambda t: t == 0)
                    ui.button('Back', on_click=lambda: (setattr(state, 'otp_sent', False), setattr(state, 'otp_timer', 0))).props('flat').classes('text-gray-500 w-full mt-2')
            else:
                ui.label('Account Active').classes('text-green-700 font-bold mt-0 ml-2 text-[10px] uppercase tracking-wider')
                ui.label(state.user_email).classes('ml-2 text-[11px] text-gray-600 mb-0')
                ui.button('Logout', on_click=logout).classes('m-1 bg-red-600 text-white w-20 h-7 text-[10px]').props('dense')
                
                # STRICT SIDEBAR RENDERING PROTECTION ENGINE (FALLBACK MATRIX)
                head_name = "Not Created"
                total_members = 0
                
                if not state.renter_id and state.user_email:
                    try:
                        fallback_res = supabase.table('renters').select('*').execute()
                        if fallback_res.data:
                            for r in fallback_res.data:
                                if str(r.get('email', '')).strip().lower() == state.user_email.lower():
                                    state.renter_id = r['id']
                                    state.room_no = r['room_no']
                                    state.active_renter_head_id = r['head_member_id']
                                    break
                    except Exception as fe:
                        print(fe)

                current_room = state.room_no if state.room_no else "-"
                
                if state.renter_id:
                    try:
                        members = supabase.table('public_members').select('name,relation,head_id').eq('renter_id', state.renter_id).execute()
                        if members.data:
                            total_members = len(members.data)
                            for m in members.data:
                                # 🔥 FIX: Mismatch se bachne ke liye text-relation base mapping engine strict kiya hai
                                if str(m.get('relation', '')).strip().lower() == 'head':
                                    head_name = m.get('name', 'Not Created')
                                    break
                    except Exception as sidebar_err:
                        print(f"Sidebar counter issue: {sidebar_err}")
                
                with ui.card().classes('mx-2 mt-2 p-2 shadow-sm border'):
                    ui.label(f"Room No : {current_room}").classes('text-xs font-bold text-gray-800')
                    ui.label(f"Head : {head_name}").classes('text-xs text-gray-700 font-medium')
                    ui.label(f"Total Members : {total_members}").classes('text-xs text-gray-700 font-medium')

                with ui.card().classes('mx-2 mt-2 p-3 shadow-sm border w-[98%] h-60 overflow-auto'):
                    ui.label('NOTICE BOARD').classes('font-bold text-orange-700 text-ms blink-text')
                    ui.separator()
                    render_notices()
        sidebar_content()
    with ui.column().classes('main-content-container w-full  mt-4 px-2'):
        @ui.refreshable
        def main_content():
            if not state.is_logged_in:
                ui.image('static/doctor.png') \
                        .classes('w-full') \
                        .style('height:auto;')
                return
                
            # REAL-TIME FALLBACK LOGIC FOR RENTER HEAD UUID MATCHING
            electric_enabled = True
            gas_enabled = True
            try:
                if state.user_email:
                    renter = supabase.table('renters').select('id,room_no,head_member_id,email,setting_tab').execute()
                    valid_row = None
                    if renter.data:
                        for r in renter.data:
                            if str(r.get('email','')).strip().lower() == state.user_email.lower():
                                valid_row = r
                                break
                    

                    if valid_row:
                        settings = valid_row.get('setting_tab') or {}
                        electric_enabled = settings.get( 'electric_history_enabled',    True )
                        gas_enabled = settings.get(  'gas_history_enabled', True)
                        state.renter_id = valid_row['id']
                        state.room_no = valid_row['room_no']
                        state.active_renter_head_id = valid_row['head_member_id']
                        if state.renter_id and not state.active_renter_head_id:
                            state.current_page = 'profile'
                            state.member_view = 'add'
            except Exception as ex:
                print(ex)
    
            if state.current_page == 'profile':
                if state.member_view == "list":
                    with ui.card().classes('p-4 w-full max-w-4xl shadow-sm mx-auto mt-2'):
                        with ui.column().classes('w-full items-center mb-4 gap-2'):
                            ui.label("Resident Family Members").classes('text-xl text-green-800 font-bold text-center w-full')
                            with ui.row().classes('w-full justify-between items-center px-1'):
                                ui.button('⬅ Back', on_click=lambda: (setattr(state, 'current_page', 'dashboard'), main_content.refresh())).props('flat dense').classes('text-green-700 font-bold text-xs')
                                ui.button('+ Add Member', on_click=lambda: (setattr(state, 'member_view', 'add'), state.dynamic_family_members.clear(), main_content.refresh())).classes('bg-green-700 text-white font-bold text-xs')
                        
                        try:
                            renter_email = ""
                            renter_res = supabase.table('renters').select('email').eq('id', state.renter_id).single().execute()
                            if renter_res.data:
                                renter_email = renter_res.data.get('email', '')

                            response = supabase.table('public_members').select('*') \
                            .eq('renter_id',state.renter_id).execute()
                            current_members = response.data if response.data else []
                            
                            # 🔥 STABLE FIXED SORTING ENGINE: Isse 'Head' text match hote hi row priority hamesha 1 ho jayegi
                            def get_sort_key(m):
                                relation_str = str(m.get('relation', '')).strip().lower()
                                is_head = (relation_str == 'head')
                                try:
                                    age = int(m.get('age')) if m.get('age') is not None else 0
                                except:
                                    age = 0
                                priority = 1 if is_head else 2
                                return (priority, -age)
                            
                            sorted_members = sorted(current_members, key=get_sort_key)
                            
                        except Exception as e:
                            ui.notify(f"Database Error: {str(e)}", type='negative')
                            sorted_members = []
                        
                        with ui.column().classes('w-full gap-2 mt-2'):
                            for member in sorted_members:
                                m_name = member.get('name', 'Unknown')
                                m_rel = member.get('relation', 'N/A')
                                status_val = str(member.get('status', 'Pending')).strip().lower()

                                if status_val == 'pending':
                                    display_title = f"🔴 {m_name} ({m_rel})"
                                else:
                                    display_title = f"{m_name} ({m_rel})"                                                              
                                with ui.expansion(display_title, icon='person').classes('w-full border shadow-xs rounded bg-white font-bold text-base text-gray-800'):
                                    with ui.element('div').classes('responsive-grid w-full p-3 text-[14px]'):
                                        def show_field(label, value, color='text-gray-600'):
                                            with ui.row().classes('items-center'):
                                                ui.label(f"{label}:").classes('font-black text-gray-900 ') # Dark & Bold Label
                                                ui.label(value).classes(f'{color} ml-1') # Normal Value

                                        show_field("Relation", member.get('relation', 'N/A'))
                                        show_field("Mobile No", member.get('mobile', 'N/A'))
                                        show_field("WhatsApp", member.get('whatsapp', 'N/A'))
                                        
                                        # 1. WhatsApp (Public Members table)
                                        status_val = member.get('status', 'Pending')
                                        s_color = 'text-green-600' if str(status_val).lower() == 'approved' else 'text-red-600'
                                        
                                        with ui.row().classes('items-center'):
                                            ui.label("Status:").classes('font-black text-gray-900')
                                            ui.label(status_val).classes(f'font-bold ml-1 {s_color}')

                                        if m_rel.lower() == 'head':
                                            ui.label(f"Email: {renter_email}").classes('text-blue-700 font-bold w-15')
                                        show_field("Age", member.get('age', 'N/A'))
                                        show_field("Gender", member.get('gender', 'N/A'))
                                        show_field("Religion", member.get('religion', 'N/A'))
                                        show_field("Aadhaar No" ,member.get('aadhaar', 'N/A'))
                                        if member.get('whatsapp'):
                                            ui.label(f"WhatsApp: {member.get('whatsapp', 'N/A')}")
                                        if member.get('occupation'):
                                            ui.label(f"Occupation: {member.get('occupation', 'N/A')}")
                                        
                                    with ui.row().classes('w-full p-3 bg-gray-50 border-t text-[14px] text-gray-700 font-normal items-center flex-wrap gap-x-4 gap-y-1'):
                                        ui.label('Address:').classes('font-bold text-gray-900 mr-2')
                                        
                                        raw_address = member.get('address', 'Meena Residency')
                                        if "PO:" in raw_address or "Dist:" in raw_address:
                                            addr_dict = {}
                                            parts = raw_address.split(',')
                                            
                                            if parts and ":" not in parts[0]:
                                                addr_dict['Vill/Flat'] = parts[0].strip()
                                                
                                            for part in parts:
                                                if ":" in part:
                                                    k, v = part.split(':', 1)
                                                    addr_dict[k.strip()] = v.strip()
                                            
                                            labels_to_show = [
                                                ('Vill/Flat', 'Vill/Flat'),
                                                ('Panchayat', 'Panchayat'),
                                                ('Block', 'Block'),
                                                ('PS', 'PS'),
                                                ('PO', 'PO'),
                                                ('Dist', 'Dist'),
                                                ('State', 'State'),
                                                ('Pin', 'Pin')
                                            ]
                                            
                                            for key_lbl, display_lbl in labels_to_show:
                                                val = addr_dict.get(key_lbl, '')
                                                if val or key_lbl in ['Vill/Flat', 'PO', 'Dist']:
                                                    with ui.row().classes('items-center no-wrap gap-1'):
                                                        ui.label(f"{display_lbl}:").classes('font-bold text-gray-900')
                                                        ui.label(val if val else 'Not Available').classes('text-gray-500 font-medium')
                                        else:
                                            ui.label(raw_address).classes('text-gray-500 font-medium')
                    
                elif state.member_view == "add":
                    with ui.column().classes('w-full max-w-2xl mx-auto mt-1 gap-4'):
                        with ui.card().classes('p-4 w-full shadow-md border-t-4 border-blue-600 bg-white'):
                            title_text = (
                                'Create Head Of Family'
                                if not state.active_renter_head_id
                                else
                                'Add Family Members'
                            )

                            ui.label(title_text)
                            @ui.refreshable
                            def sub_members_ui():
                                if not state.dynamic_family_members:

                                    if not state.active_renter_head_id:

                                        state.dynamic_family_members.append({
                                            'name_v': '',
                                            'rel_v': 'Head',
                                            'gen_v': 'Male',
                                            'age_v': '',
                                            'mob_v': '',
                                            'adh_v': '',
                                            'show_so': False,
                                            'show_staff_so': False,
                                            'show_addr': True
                                        })

                                    else:

                                        state.dynamic_family_members.append({
                                            'name_v': '',
                                            'rel_v': 'Wife',
                                            'gen_v': 'Female',
                                            'age_v': '',
                                            'mob_v': '',
                                            'adh_v': '',
                                            'show_so': False,
                                            'show_staff_so': False,
                                            'show_addr': False
                                        })

                                for idx, m_state in enumerate(state.dynamic_family_members):
                                    with ui.row().classes('w-full items-center justify-between my-2 bg-blue-50 p-1 rounded border-l-4 border-blue-500'):
                                        ui.label(f"Family Member #{idx + 1} Fields").classes('text-xs font-bold text-blue-800')
                                        if len(state.dynamic_family_members) > 1:
                                            ui.button('X', on_click=lambda i=idx: (state.dynamic_family_members.pop(i), sub_members_ui.refresh())).classes('bg-red-600 text-white font-bold text-[10px] px-2 py-0.5 rounded shadow-sm')
                                    
                                    with ui.card().classes('w-full p-3 bg-gray-50 border border-gray-200 rounded-lg shadow-inner mb-2'):
                                        def on_sub_rel_change(e, s=m_state):
                                            s['rel_v'] = e.value
                                            s['show_so'] = e.value == 'Husband'
                                            s['show_staff_so'] = e.value in ['Staff', 'Others']
                                            s['show_addr'] = e.value in ['Staff', 'Others']
                                            sub_members_ui.refresh()

                                        with ui.grid(columns=2).classes('w-full gap-2 p-3 text-[14px]'):
                                            ui.input('Member Name').props('outlined dense').bind_value(m_state, 'name_v')
                                            if not state.active_renter_head_id:
                                                rel_input = ui.input('Relation', value='Head').props('outlined dense readonly' )
                                                m_state['rel_v'] = 'Head'
                                            else:
                                                ui.select(
                                                    [
                                                        'Wife',
                                                        'Husband',
                                                        'Son',
                                                        'Daughter',
                                                        'Grandfather',
                                                        'Grandmother',
                                                        'Grandson',
                                                        'Granddaughter',
                                                        'Staff',
                                                        'Others'],
                                                    label='Relation',value=m_state['rel_v'],on_change=lambda e, s=m_state: on_sub_rel_change(e, s)).props('outlined dense')
                                                                                                                                        
                                        if m_state.get('show_so'):
                                            with ui.grid(columns=2).classes('w-full gap-2 mt-2'):
                                                with ui.row().classes('w-full gap-1 items-center no-wrap'):
                                                    ui.select(['S/O'], value=m_state.get('so_t','S/O')).props('outlined dense').classes('w-20').on('value_change', lambda e, s=m_state: s.update({'so_t': e.value}))
                                                    ui.input('Father Name').props('outlined dense placeholder="Father\'s name"').classes('flex-grow').bind_value(m_state, 'son_v')

                                        if m_state.get('show_staff_so'):
                                            with ui.grid(columns=2).classes('w-full gap-2 mt-2'):
                                                with ui.row().classes('w-full gap-2 items-center'):
                                                        ui.select(  ['S/O', 'W/O'], value=m_state.get('st_so_t','S/O')).props('outlined dense').classes('w-24')
                                                        ui.input('Relative Name')\
                                                            .props('outlined dense placeholder="Enter name"')\
                                                            .classes('flex-grow min-w-[220px]')
                                        with ui.grid(columns=2).classes('w-full gap-2 mt-2'):
                                            ui.select(['Female', 'Male', 'Other'], label='Gender', value=m_state['gen_v']).props('outlined dense').on('value_change', lambda e, s=m_state: s.update({'gen_v': e.value}))
                                            ui.input('Age').props('outlined dense type="number" inputmode="numeric"').bind_value(m_state, 'age_v')
                                            ui.input('Mobile').props('outlined dense  type="tel" inputmode="numeric" mask="##########"').bind_value(m_state, 'mob_v')
                                            ui.input('Aadhaar').props('outlined dense type="tel" inputmode="numeric"  mask="####-####-####"').bind_value(m_state, 'adh_v')
                                        
                                        if m_state.get('show_addr'):
                                            with ui.column().classes('w-full mt-2 p-2 bg-white rounded border border-emerald-100'):
                                                ui.select( ['Hindu', 'Muslim', 'Christian'],  label='Religion').props('outlined dense') .classes('w-full') \
                                                .bind_value(m_state, 'relig_v')
                                                ui.label('Address Details').classes('text-[10px] font-bold text-emerald-600')
                                                with ui.grid(columns=2).classes('w-full gap-2'):
                                                    ui.input('Village / Flat No').props('outlined dense').bind_value(m_state, 'v_v')
                                                    ui.input('Panchayat').props('outlined dense').bind_value(m_state, 'panch_v')
                                                    ui.input('Block').props('outlined dense').bind_value(m_state, 'block_v')
                                                    ui.input('Police Station (PS)').props('outlined dense').bind_value(m_state, 'ps_v')
                                                    ui.input('Post Office (PO)').props('outlined dense').bind_value(m_state, 'po_v')
                                                    ui.input('District').props('outlined dense').bind_value(m_state, 'dt_v')
                                                    INDIA_STATES = ['Andhra Pradesh', 'Arunachal Pradesh', 'Assam','Bihar','Chhattisgarh','Goa','Gujarat',
                                                            'Haryana',   'Himachal Pradesh','Jharkhand','Karnataka',
                                                            'Kerala', 'Madhya Pradesh','Maharashtra',
                                                            'Manipur', 'Meghalaya',  'Mizoram','Nagaland','Odisha',  'Punjab', 'Rajasthan', 'Sikkim','Tamil Nadu','Telangana', 'Tripura',  'Uttar Pradesh','Uttarakhand',  'West Bengal']

                                                    ui.select(INDIA_STATES,label='State').props('outlined dense').bind_value(m_state, 'st_v')
                                                    ui.input('Pincode').props('outlined dense type="tel" inputmode="numeric" ').bind_value(m_state, 'pin_v')
                            sub_members_ui()

                            def add_fam():
                                if len(state.dynamic_family_members) < 5:
                                    state.dynamic_family_members.append({'name_v': '', 'rel_v': 'Wife', 'gen_v': 'Female', 'age_v': '', 'mob_v': '', 'adh_v': '', 'show_so': False, 'show_staff_so': False, 'show_addr': False})
                                    sub_members_ui.refresh()

                            ui.button('Add more Member', on_click=add_fam).classes('bg-blue-600 text-white font-bold text-xs rounded h-8 mx-auto block my-3')

                        def save_all():
                            if not state.dynamic_family_members:
                                ui.notify('Please add at least one member form.', type='warning')
                                return

                            has_valid_member = any(str(m.get('name_v', '')).strip() != '' for m in state.dynamic_family_members)
                            if not has_valid_member:
                                ui.notify('At least one Member Name is required to save!', type='warning')
                                return
                            
                            try:
                                family_payload = []
                                for m in state.dynamic_family_members:
                                    member_name = str(m.get('name_v', '')).strip()
                                    if not member_name:
                                        continue
                                        
                                    r_val = m.get('rel_v', 'Wife')
                                    
                                    if r_val in ['Wife', 'Son', 'Daughter', 'Husband', 'Grandfather', 'Grandmother', 'Grandson', 'Granddaughter']:
                                        sub_addr = "Same as Head"
                                    elif m.get('show_addr'):
                                        sub_addr = f"{m.get('v_v','')}, Panchayat: {m.get('panch_v','')}, Block: {m.get('block_v','')}, PO: {m.get('po_v','')}, PS: {m.get('ps_v','')}, Dist: {m.get('dt_v','')}, State: {m.get('st_v','')}, Pin: {m.get('pin_v','')}"
                                        sub_addr = sub_addr.strip().strip(',')
                                    else:
                                        sub_addr = "Same as Head"
                                    
                                    if r_val == 'Husband':
                                        rel_name_str = str(m.get('son_v', '')).strip()
                                        rel_prefix = m.get('so_t', 'S/O')
                                    elif r_val in ['Staff', 'Others']:
                                        rel_name_str = str(m.get('st_so_n', '')).strip()
                                        rel_prefix = m.get('st_so_t', 'S/O')
                                    else:
                                        rel_name_str = ""
                                        rel_prefix = ""
                                    
                                    father_husband = f"{rel_prefix} - {rel_name_str}" if rel_name_str else None
                                    
                                    mob_clean = str(m.get('mob_v', '')).strip()
                                    adh_clean = str(m.get('adh_v', '')).strip()

                                    head_id_to_save = (
                                        state.active_renter_head_id
                                        if state.active_renter_head_id
                                        else None
                                    )
                                    
                                    row_data = {
                                        "name": member_name, 
                                        "relation": r_val, 
                                        "father_husband_name": father_husband,
                                        "age": int(m['age_v']) if m.get('age_v') and str(m['age_v']).isdigit() else None,
                                        "gender": m.get('gen_v', 'Female'),
                                        "mobile": mob_clean if mob_clean else None, 
                                        "whatsapp": None, 
                                        "aadhaar": adh_clean if (adh_clean and adh_clean != "--") else None,
                                        "religion": str(m.get('relig_v', '')).strip() or 'N/A',
                                        "occupation": None, 
                                        "address": sub_addr,
                                        "head_id": head_id_to_save,
                                        "renter_id": state.renter_id,
                                        "status": "Pending"
                                                                              
                                    }

                                    family_payload.append(row_data)
                                
                                if family_payload:
                                    insert_response = supabase.table('public_members').insert(family_payload).execute()
                                    if not state.active_renter_head_id:
                                            head_uuid = insert_response.data[0]['id']
                                            supabase.table('renters').update({'head_member_id': head_uuid}).eq('id',state.renter_id).execute()
                                            state.active_renter_head_id = head_uuid
                                            renter_check = supabase.table(
                                                'renters'
                                            ).select(
                                                'head_member_id'
                                            ).eq(
                                                'id',
                                                state.renter_id
                                            ).single().execute()

                                            state.active_renter_head_id = renter_check.data['head_member_id']
                                            state.current_page = "dashboard"
                                            state.member_view = "list"
                                            sidebar_content.refresh()
                                    ui.notify(f'{len(family_payload)} Family Member(s) Saved successfully!', type='positive')
                                    state.member_view = "list"
                                    sidebar_content.refresh() # Update sidebar layout on save
                                    main_content.refresh()
                                else:
                                    ui.notify('No valid rows with names found to save!', type='warning')
                                
                            except Exception as ex:
                                ui.notify(f"Database Error: {str(ex)}", type='negative')

                        with ui.row().classes('w-full mt-2 gap-2 mb-6'):
                            ui.button('SAVE RECORD', on_click=save_all).classes('bg-green-700 text-white flex-grow font-bold text-xs h-9')
                            ui.button('CANCEL', on_click=lambda: (setattr(state, 'member_view', 'list'), main_content.refresh())).classes('bg-gray-400 text-white text-xs h-9')

            elif state.current_page == 'billing':
                with ui.card().classes('p-4 w-full max-w-4xl shadow-md mx-auto mt-2 bg-white'):
                    ui.button('⬅ Back Dashboard', on_click=lambda: (setattr(state, 'current_page', 'dashboard'), main_content.refresh())).props('flat dense').classes('mb-2 text-green-700 font-bold text-xs')
                    ui.label(f'{state.bill_type} Ledger').classes('text-xl text-green-800 font-bold mb-1 text-center w-full')
                    
                    with ui.row().classes('w-full justify-between gap-2 border-b pb-2 mb-4'):
                        ui.button('📅 Current Month', on_click=lambda: (setattr(state, 'billing_tab', 'current'), main_content.refresh())) \
                            .classes('flex-grow font-bold text-xs h-9') \
                            .props(f'flat' if state.billing_tab != 'current' else 'unelevated color="green-700"')
                        
                        ui.button('📜 History', on_click=lambda: (setattr(state, 'billing_tab', 'history'), main_content.refresh())) \
                            .classes('flex-grow font-bold text-xs h-9') \
                            .props(f'flat' if state.billing_tab != 'history' else 'unelevated color="green-700"')

                    if state.billing_tab == "current":
                        c_prev_read = "Not Available"
                        c_prev_date = "Not Available"
                        
                        if state.active_renter_head_id:
                            try:
                                last_bill_resp = supabase.table('utility_billing_ledger') \
                                    .select('curr_reading,curr_reading_date,bill_month,bill_year') \
                                    .eq('room_no', state.room_no) \
                                    .eq('bill_type', state.bill_type) \
                                    .order('bill_year', desc=True) \
                                    .order('curr_reading_date', desc=True) \
                                    .limit(1) \
                                    .execute()
                                    
                                
                                if last_bill_resp.data and last_bill_resp.data[0].get('curr_reading') is not None:
                                    c_prev_read = last_bill_resp.data[0].get('curr_reading')
                                    raw_p_date = last_bill_resp.data[0].get('curr_reading_date')
                                    c_prev_date = datetime.strptime(raw_p_date, "%Y-%m-%d").strftime("%d-%b-%Y") if raw_p_date else "Not Available"
                            except:
                                pass
                            
                            # --- LOCKED DATABASE CHECK (Bypasses overwrite if memory is already True) ---
                            current_bill_row = None

                            try:
                                check_exists = supabase.table(
                                    'utility_billing_ledger'
                                ).select('*') \
                                .eq('renter_id', state.renter_id) \
                                .eq('bill_type', state.bill_type) \
                                .eq('bill_month', state.selected_month) \
                                .eq('bill_year', datetime.now().year) \
                                .order('created_at', desc=True) \
                                .limit(1) \
                                .execute()

                                if check_exists.data:
                                    current_bill_row = check_exists.data[0]

                            except Exception as ex:
                                print(ex)
                                
                                
                        c_today_date = datetime.now().strftime("%d-%b-%Y")

                        with ui.column().classes('w-full gap-2 items-center'):
                            with ui.row().classes('w-full justify-center bg-emerald-50 border border-emerald-200 rounded p-2 mb-1'):
                                ui.label('Current Billing Month:').classes('font-bold text-emerald-900 text-sm mr-1')
                                ui.label(f"{state.selected_month} 2026").classes('font-extrabold text-emerald-700 text-sm')
                            
                            # --- STATUS BAR ---
                            if not current_bill_row:
                                current_status = "Pending at Renter"
                            else:
                                current_status = current_bill_row.get(   'status', 'Submitted')
                            status_colors = {"Pending at Renter": "bg-red-600", "Submitted": "bg-yellow-500", "Approved": "bg-green-600"}
                            text_colors = {"Pending at Renter": "text-red-700", "Submitted": "text-yellow-700", "Approved": "text-green-700"}
                            current_color = status_colors.get(  current_status, "bg-gray-400")
                            with ui.column().classes('w-full items-center my-2 gap-1 px-4 max-w-xl'):
                                with ui.row().classes('w-full bg-gray-200 relative items-center').style('height: 6px; border-radius: 3px;'):
                                    fill_percent = (  "w-1/3"
                                        if current_status == "Pending at Renter"
                                        else ( "w-2/3"
                                            if current_status == "Submitted"
                                            else "w-full"))
                                    ui.label().classes(f'absolute top-0 left-0 h-full {current_color} {fill_percent}').style('border-radius: 3px;')
                                
                                with ui.row().classes('w-full justify-between text-[11px] font-bold uppercase tracking-wider text-gray-400 mt-1'):
                                    ui.label('Pending').classes(text_colors['Pending at Renter'] if current_status == "Pending at Renter" else '')
                                    ui.label('Submitted').classes(text_colors['Submitted'] if current_status == "Submitted" else '')
                                    ui.label('Approved').classes(text_colors['Approved'] if current_status == "Approved" else '')

                            # --- CURRENT MONTH CARD BOX ---
                            with ui.card().classes('w-full p-4 border rounded-lg bg-gray-50 shadow-inner mt-1'):
                                ui.label( f"Log Details for {state.selected_month} 2026"  ).classes( 'text-sm font-bold text-emerald-800 mb-3 border-b pb-1 w-full' )
                                # =========================
                                # DB ROW FOUND
                                # =========================
                                if current_bill_row:
                                    prev_reading = current_bill_row.get('prev_reading')
                                    curr_reading = current_bill_row.get('curr_reading')
                                    prev_date_raw = current_bill_row.get('prev_reading_date')
                                    curr_date_raw = current_bill_row.get('curr_reading_date')
                                    prev_date = ( datetime.strptime(  prev_date_raw, "%Y-%m-%d"   ).strftime("%d-%b-%Y")  if prev_date_raw else "Not Available" )
                                    curr_date = ( datetime.strptime(  curr_date_raw,  "%Y-%m-%d" ).strftime("%d-%b-%Y") if curr_date_raw else "Not Available")
                                    consumed_units = current_bill_row.get(  'total_consumed_units','Not Available'  )
                                    extra_units = current_bill_row.get( 'extra_units', 0 )
                                    rate = current_bill_row.get('rate_per_unit')                                                                                                  
                                    total_amount = current_bill_row.get(  'total_amount',  'Not Available' )
                                    # Meter Photo Preview
                                    bill_img = current_bill_row.get('bill_img_url')
                                    if bill_img:
                                            ui.image(  bill_img  ).classes( 'w-full rounded-lg border' ).style( 'max-height:320px; ')
                                   
                                    with ui.grid(columns=2).classes(
                                        'w-full gap-y-4 text-[14px] text-gray-700'):
                                        with ui.column().classes('gap-0'):
                                            ui.label('Previous Reading:').classes(  'font-bold text-gray-900')
                                            ui.label(prev_date).classes('text-blue-600 font-bold text-[11px]')
                                            ui.label( f"{prev_reading} KWh" ).classes( 'text-gray-500 font-medium' )
                                        with ui.column().classes('gap-0'):
                                            ui.label('Current Reading:').classes( 'font-bold text-gray-900')
                                            ui.label(curr_date).classes( 'text-blue-600 font-bold text-[11px]')
                                            ui.label( f"{curr_reading} KWh"  ).classes( 'text-emerald-700 font-bold' )
                                        with ui.row().classes('items-center gap-1'):
                                            ui.label(  'Consumed Unit:' ).classes( 'font-bold text-gray-900')
                                            ui.label( f"{consumed_units} Units").classes('text-emerald-700 font-bold' )
                                        with ui.row().classes('items-center gap-1'):
                                            ui.label(  'Extra Unit:').classes( 'font-bold text-gray-900')
                                            ui.label( str(extra_units) ).classes(  'text-gray-500 font-medium'  )
                                        with ui.row().classes('items-center gap-1'):
                                            ui.label(  'Rate:'  ).classes( 'font-bold text-gray-900' )
                                            ui.label( f"₹ {float(rate):.2f}" if rate is not None  else "")                                                                                                                                 
                                        with ui.row().classes('items-center gap-1'):
                                            ui.label('Total Amount:' ).classes(  'font-bold text-gray-900'   )
                                            ui.label( f"₹ {float(total_amount):.2f}"   if total_amount is not None   else " " ).classes( 'text-orange-700 font-black text-base' )
                                    ui.separator().classes('my-2')
                                    status_text = str( current_bill_row.get('status', 'Submitted')).upper()
                                    status_color = (  'text-green-700'   if status_text == 'APPROVED'  else 'text-red-700')
                                    bg_color = (  'bg-green-50 border-green-200'   if status_text == 'APPROVED'   else 'bg-red-50 border-red-200')
                                    with ui.row().classes(  f'w-full justify-center border rounded p-2 {bg_color}'):
                                        ui.label(status_text).classes( f'{status_color} font-black text-sm uppercase tracking-wider')

                                # =========================
                                # NO ROW FOUND
                                # =========================
                                else:

                                    with ui.grid(columns=2).classes('w-full gap-y-4 text-[14px] text-gray-700 mb-4' ):
                                        with ui.column().classes('gap-0'):
                                            ui.label('Previous Reading:').classes(  'font-bold text-gray-900')
                                            ui.label(c_prev_date).classes( 'text-blue-600 font-bold text-[11px]')
                                            ui.label(  f"{c_prev_read} KWh" if c_prev_read != "Not Available"    else "Not Available" ).classes('text-gray-500 font-medium' )
                                        with ui.column().classes('gap-0'):
                                            ui.label('Current Month:').classes( 'font-bold text-gray-900' )
                                            ui.label(c_today_date).classes(  'text-blue-600 font-bold text-[11px]' )
                                            ui.label( "0 KWh (Pending Input)"  ).classes(  'text-gray-500 font-medium' )
                                        with ui.row().classes('items-center gap-1'):
                                            ui.label('Extra Unit:').classes( 'font-bold text-gray-900'  )
                                            ui.label('0').classes(    'text-gray-500 font-medium' )
                                    with ui.row().classes(
                                        'w-full mt-2 justify-center'):
                                        kwh_input = ui.input( 'Enter KWh Reading' ).props('outlined dense type="number"' ).classes('w-full max-w-md bg-white shadow-xs')
                                                      
                            # --- SUBMIT FUNCTION ---
                            def trigger_submit():
                                try:
                                    existing = supabase.table(
                                        'utility_billing_ledger'
                                    ).select(
                                        'id'
                                    ).eq(
                                        'renter_id',
                                        state.renter_id
                                    ).eq(
                                        'bill_type',
                                        state.bill_type
                                    ).eq(
                                        'bill_month',
                                        state.selected_month
                                    ).eq(
                                        'bill_year',
                                        datetime.now().year
                                    ).limit(1).execute()

                                    if existing.data:
                                        ui.notify('Already Submitted', type='warning')
                                        return
                                except Exception as ex:
                                    print(ex)

                                if state.is_submitted:
                                    ui.notify('Log already submitted for this month!', type='warning')
                                    return
                                if not state.active_renter_head_id:
                                    ui.notify('Error: Active Family Head ID missing!', type='negative')
                                    return
                                if not kwh_input.value:
                                    ui.notify('Please enter KWh reading!', type='warning')
                                    return
                                    
                                try:
                                    db_prev_val = float(c_prev_read) if c_prev_read != "Not Available" else 0.0
                                    
                                    payload = {
                                        "renter_id": state.renter_id,
                                        "room_no": state.room_no,
                                        "head_id": state.active_renter_head_id,
                                        "bill_type": state.bill_type,
                                        "bill_month": state.selected_month,
                                        "bill_year": datetime.now().year,
                                        "prev_reading": db_prev_val,
                                        "prev_reading_date": datetime.strptime(c_prev_date, "%d-%b-%Y").strftime("%Y-%m-%d") if '-' in str(c_prev_date) else None,
                                        "curr_reading": float(kwh_input.value),
                                        "curr_reading_date": datetime.now().strftime("%Y-%m-%d"),
                                        "status": "Submitted",
                                        "rate_per_unit": None,
                                        "bill_img_url": None
                                    }
                                    
                                    state.submitted_kwh = str(kwh_input.value)
                                    state.is_submitted = True
                                    state.bill_status = "Submitted"
                                    
                                    supabase.table('utility_billing_ledger').insert(payload).execute()
                                    ui.notify("Logged and Inserted to Database successfully!", type='positive')
                                    main_content.refresh()
                                    
                                except Exception as e:
                                    state.is_submitted = False
                                    state.bill_status = "Pending at Renter"
                                    ui.notify(f"Submission Failed: {str(e)}", type='negative')

                            if not current_bill_row:
                                ui.button('SUBMIT LOG',on_click=trigger_submit  ).classes('w-full mt-4 bg-green-700 text-white font-bold h-10 text-xs').disable()
                            
                    elif state.billing_tab == "history":
                        approved_history = supabase.table( 'utility_billing_ledger').select('bill_month,bill_year').eq('renter_id', state.renter_id).eq('bill_type', state.bill_type).eq( 'status', 'Approved').execute()
                        with ui.column().classes('w-full gap-3 items-center'):
                            allowed_history_months = []

                            if approved_history.data:
                                allowed_history_months = list(dict.fromkeys([row['bill_month'] for row in approved_history.data]   ))
                            allowed_history_months.sort( key=lambda m: ['January','February','March','April','May','June', 'July','August','September','October','November','December' ].index(m))
                            if not allowed_history_months:
                              ui.label( 'No Approved Bills Available' ).classes('text-red-600 font-bold')
                              return
                            if state.history_month not in allowed_history_months:
                                state.history_month = allowed_history_months[-1]
                                
                            ui.select(allowed_history_months, value=state.history_month, label="Select History Month", 
                                      on_change=lambda e: (setattr(state, 'history_month', e.value), main_content.refresh())).props('outlined dense').classes('w-full max-w-md')
                            
                            prev_reading = "Not Available"
                            curr_reading = "Not Available"
                            p_date_mock = "Not Available"
                            c_date_mock = "Not Available"
                            consumed_units = "Not Available"
                            extra_units = 0
                            rate_per_unit = None
                            total_amount = "Not Available"

                            if state.active_renter_head_id:
                                try:
                                    history_resp = supabase.table('utility_billing_ledger') \
                                        .select('*') \
                                        .eq('renter_id',state.renter_id) \
                                        .eq('bill_type', state.bill_type) \
                                        .eq('bill_month', state.history_month) \
                                        .eq('status', 'Approved') \
                                        .limit(1) \
                                        .execute()
                                    
                                    if history_resp.data:
                                        history_record = history_resp.data[0]
                                        prev_reading = history_record.get('prev_reading')
                                        curr_reading = history_record.get('curr_reading')
                                        p_date_raw = history_record.get('prev_reading_date')
                                        c_date_raw = history_record.get('curr_reading_date')
                                        
                                        p_date_mock = datetime.strptime(p_date_raw, "%Y-%m-%d").strftime("%d-%b-%Y") if p_date_raw else 'Not Available'
                                        c_date_mock = datetime.strptime(c_date_raw, "%Y-%m-%d").strftime("%d-%b-%Y") if c_date_raw else 'Not Available'
                                        
                                        consumed_units = history_record.get('total_consumed_units')
                                        extra_units = history_record.get('extra_units', 0)
                                        rate_per_unit = history_record.get('rate_per_unit')
                                        total_amount = history_record.get('total_amount')
                                        history_bill_img = history_record.get('bill_img_url')                             
                                except:
                                    pass
                            
                            with ui.card().classes('w-full p-4 border rounded-lg bg-gray-50 mt-2 shadow-inner'):
                                ui.label(f"Billing Details for {state.history_month} 2026").classes('text-sm font-bold text-emerald-800 mb-3 border-b pb-1 w-full')
                                if history_bill_img:
                                        ui.image(  history_bill_img ).classes( 'w-full rounded-lg border mb-3' ).style(  'max-height:320px; object-fit:contain;')

                                with ui.grid(columns=2).classes('w-full gap-y-4 text-[14px] text-gray-700'):
                                    with ui.column().classes('gap-0'):
                                        ui.label('Previous Reading:').classes('font-bold text-gray-900')
                                        ui.label(p_date_mock).classes('text-blue-600 font-bold text-[11px]')
                                        ui.label(f"{prev_reading} KWh" if prev_reading != "Not Available" else "Not Available").classes('text-gray-500 font-medium')
                                        
                                    with ui.column().classes('gap-0'):
                                        ui.label('Current Month:').classes('font-bold text-gray-900')
                                        ui.label(c_date_mock).classes('text-blue-600 font-bold text-[11px]')
                                        ui.label(f"{curr_reading} KWh" if curr_reading != "Not Available" else "Not Available").classes('text-gray-500 font-medium')
                                        
                                    with ui.row().classes('items-center gap-1'):
                                        ui.label('Total Consumed Unit:').classes('font-bold text-gray-900')
                                        ui.label(f"{consumed_units} Units" if consumed_units != "Not Available" else "Not Available").classes('text-emerald-700 font-bold')
                                        
                                    with ui.row().classes('items-center gap-1'):
                                        ui.label('Extra Unit:').classes('font-bold text-gray-900')
                                        ui.label(f"{extra_units}").classes('text-gray-500 font-medium')
                                        
                                    with ui.row().classes('items-center gap-1'):
                                        ui.label('Rate:').classes('font-bold text-gray-900')
                                        ui.label(  f"₹ {float(rate_per_unit):.2f}" if rate_per_unit is not None    else "").classes('text-gray-500 font-medium')
                                    with ui.row().classes('items-center gap-1'):
                                        ui.label('Total Amount:').classes('font-bold text-gray-900')
                                        ui.label(  f"₹ {float(total_amount):.2f}" if total_amount is not None else "").classes(  'text-orange-700 font-black text-base')
            elif state.current_page == 'renting':
                with ui.card().classes('p-4 w-full max-w-4xl shadow-md mx-auto mt-2 bg-white'):
                    ui.button('⬅ Back Hub', on_click=lambda: (setattr(state, 'current_page', 'dashboard'), main_content.refresh())).props('flat dense').classes('mb-2 text-green-700 font-bold text-xs')
                    ui.label('Rent Ledger').classes('text-xl text-green-800 font-bold mb-1 text-center w-full')
                    
                    with ui.row().classes('w-full justify-between gap-2 border-b pb-2 mb-4'):
                        ui.button('📅 Current Month',on_click=lambda: ( setattr(state, 'rent_tab', 'current'),main_content.refresh())).classes( 'flex-grow font-bold text-xs h-9').props('unelevated color="green-700"' if state.rent_tab == 'current'  else 'flat')
                        ui.button('📜 History',    on_click=lambda: (setattr(state, 'rent_tab', 'history'),main_content.refresh()  )).classes( 'flex-grow font-bold text-xs h-9').props(  'unelevated color="green-700"'  if state.rent_tab == 'history'  else 'flat')
                    if state.rent_tab == 'current':
                        rent_row = None
                        try:
                            resp = supabase.table('rent_ledger').select('*').eq('renter_id', state.renter_id).eq('bill_month', state.selected_month).eq('bill_year', datetime.now().year).limit(1).execute()
                            if resp.data:
                                rent_row = resp.data[0]
                        except Exception as ex:
                            print(ex)
                            
                        with ui.card().classes('w-full p-4 border rounded-lg bg-gray-50'):
                            ui.label(f"Rent Details For {state.selected_month} {datetime.now().year}").classes('font-bold text-green-800 mb-3')
                            if rent_row:
                                with ui.row().classes('items-center gap-1'):
                                        ui.label('Flat Bill :').classes(   'font-bold text-gray-900')
                                        ui.label( f"₹ {rent_row.get('flat_bill',0)}"   ).classes('text-gray-500 font-medium')
                                with ui.row().classes('items-center gap-1'):
                                    ui.label('Electric Bill :').classes('font-bold text-gray-900')
                                    ui.label(f"₹ {rent_row.get('electric_bill',0)}"  ).classes('text-gray-500 font-medium')
                                with ui.row().classes('items-center gap-1'):
                                    ui.label('Gas Bill :').classes('font-bold text-gray-900')
                                    ui.label(f"₹ {rent_row.get('gas_bill',0)}").classes('text-gray-500 font-medium')
                                with ui.row().classes('items-center gap-1'):
                                    ui.label('Other Charge :').classes('font-bold text-gray-900')
                                    ui.label(f"₹ {rent_row.get('other_charge',0)}"   ).classes('text-gray-500 font-medium')
                                ui.separator()
                                ui.label(f"Total Charge : ₹ {rent_row.get('total_charge',0)}").classes('text-orange-700 font-black text-lg')
                                ui.label( f"Status : {rent_row.get('status','Pending')}").classes('text-green-700 font-bold')
                            else:
                                ui.label('Rent Not Generated Yet').classes('text-red-600 font-bold')
                                
                    elif state.rent_tab == 'history':
                        history_months = supabase.table( 'rent_ledger').select( 'bill_month,bill_year').eq( 'renter_id', state.renter_id).execute()
                        month_options = []
                        if history_months.data:
                            month_options = list(dict.fromkeys([f"{r['bill_month']} - {r['bill_year']}"  for r in history_months.data]))
                        if not month_options:
                            ui.label(  'No Rent History Found' ).classes(  'text-red-600 font-bold')
                            return
                        if state.history_month not in month_options:
                            state.history_month = month_options[-1]
                        ui.select(month_options,    value=state.history_month,  label='Select Month', on_change=lambda e: (setattr(state, 'history_month', e.value),  main_content.refresh() )).props('outlined dense').classes('w-full max-w-md')
                        selected_month, selected_year = [x.strip() for x in state.history_month.split('-')]
                        hist = None
                        try:
                            resp = supabase.table('rent_ledger').select('*').eq('renter_id', state.renter_id).eq( 'bill_month', selected_month).eq(  'bill_year', int(selected_year)).limit(1).execute()
                            if resp.data:
                                hist = resp.data[0]
                        except Exception as ex:
                            print(ex)
                            
                        with ui.card().classes('w-full p-4 border rounded-lg bg-gray-50 mt-2'):
                            if hist:
                                ui.label(f"{state.history_month}").classes('font-bold text-green-800 mb-3').classes('font-bold text-gray-900')
                                with ui.row().classes('items-center gap-1'):
                                        ui.label('Flat Bill :').classes(   'font-bold text-gray-900')
                                        ui.label( f"₹ {hist.get('flat_bill',0)}"   ).classes('text-gray-500 font-medium')
                                with ui.row().classes('items-center gap-1'):
                                    ui.label('Electric Bill :').classes('font-bold text-gray-900')
                                    ui.label(f"₹ {hist.get('electric_bill',0)}"  ).classes('text-gray-500 font-medium')
                                with ui.row().classes('items-center gap-1'):
                                    ui.label('Gas Bill :').classes('font-bold text-gray-900')
                                    ui.label(f"₹ {hist.get('gas_bill',0)}").classes('text-gray-500 font-medium')
                                with ui.row().classes('items-center gap-1'):
                                    ui.label('Other Charge :').classes('font-bold text-gray-900')
                                    ui.label(f"₹ {hist.get('other_charge',0)}"   ).classes('text-gray-500 font-medium')
                                ui.separator()
                                ui.label(f"Total Charge : ₹ {hist.get('total_charge',0)}").classes('text-orange-700 font-black text-lg')
                                ui.label(f"Status : {hist.get('status','Pending')}").classes('text-green-600 font-bold')
                            else:
                                ui.label('No History Found').classes('text-red-700 font-bold')             
            
            elif state.current_page == 'payment':
                    ui.button(  '⬅ Back Dashboard',  on_click=lambda: (  setattr(state, 'current_page', 'dashboard'),main_content.refresh()  ) ).props('flat dense').classes('mb-2 text-green-700 font-bold text-xs')
                    ui.html("""
                                    <div style="
                                        overflow:hidden;
                                        white-space:nowrap;
                                        width:100%;
                                        color:#d97706;
                                        font-weight:bold;
                                        font-size:14px;
                                    ">
                                        <div style="
                                            display:inline-block;
                                            padding-left:100%;
                                            animation: marquee 12s linear infinite;
                                        ">
                                            Please Refresh This Page After Payment
                                        </div>
                                    </div>

                                    <style>
                                    @keyframes marquee {
                                        from {
                                            transform: translateX(0%);
                                        }
                                        to {
                                            transform: translateX(-100%);
                                        }
                                    }
                                    </style>
                                    """)
                    ui.label( 'Pay Rent').classes('text-xl text-green-800 font-bold mb-3 text-center w-full')
                    month_rows = supabase.table(   'rent_ledger' ).select( 'bill_month,bill_year'  ).eq( 'renter_id', state.renter_id ).eq( 'room_no', state.room_no).execute()
                    month_options = []
                    month_rows.data.sort( key=lambda r: (r['bill_year'],datetime.strptime(r['bill_month'],  '%B').month  ))

                    if month_rows.data:
                        month_options = list( dict.fromkeys( [  f"{r['bill_month']} - {r['bill_year']}" for r in month_rows.data   ]) )
                    if not month_options:
                        ui.label(  'No Rent Available' ).classes('text-red-600 font-bold' )
                        return
                    if state.pay_month not in month_options:
                        state.pay_month = month_options[-1]
                    ui.select( month_options,  value=state.pay_month,  label='Select Month' ).props( 'outlined dense'  ).classes(   'w-full max-w-md' ).on( 'update:model-value', lambda e: ( setattr(state, 'pay_month', e.value),  main_content.refresh()) )
                    selected_month, selected_year = [
                        x.strip()
                        for x in state.pay_month.split('-')]
                    bill = None
                    resp = supabase.table('rent_ledger'
                    ).select('*') \
                    .eq('renter_id', state.renter_id) \
                    .eq('room_no', state.room_no) \
                    .eq('bill_month', selected_month) \
                    .eq('bill_year', int(selected_year)) \
                    .limit(1) \
                    .execute()
                    if resp.data:
                        bill = resp.data[0]
                    def proceed_payment():
                            try:
                                verify = supabase.table(
                                    'rent_ledger'
                                ).select(
                                    'id,total_charge'
                                ).eq(
                                    'renter_id', state.renter_id
                                ).eq(
                                    'room_no', state.room_no
                                ).eq(
                                    'bill_month', selected_month
                                ).eq(
                                    'bill_year', int(selected_year)
                                ).limit(1).execute()

                                if not verify.data:
                                    ui.notify(
                                        'Bill mismatch detected',
                                        type='negative'
                                    )
                                    return

                                row = verify.data[0]

                                supabase.table('rent_ledger').update({

                                    'deposite': row.get('total_charge', 0),
                                    'deposit_date': datetime.now().strftime('%Y-%m-%d'),
                                    'deposit_status': 'Pending'
                                    
                                }).eq(  'id',row['id']).execute()
                                upi_link = (
                                    f"upi://pay?"
                                    f"pa=9771380098@ibl"
                                    f"&pn=Meena Residency"
                                    f"&am={row.get('total_charge',0)}"
                                    f"&cu=INR") 
                                ui.run_javascript(f'window.location.href="{upi_link}"')

                               
                                                            

                            except Exception as ex:
                                ui.notify(
                                    str(ex),
                                    type='negative'
                                )
                    if bill:
                        with ui.card().classes('w-full p-4 border rounded-lg bg-gray-50 mt-3'):
                            ui.label(state.pay_month).classes('font-bold text-green-800 mb-3')
                            with ui.row().classes('items-center gap-1'):
                                ui.label('Flat Bill :').classes('font-bold')
                                ui.label(f"₹ {bill.get('flat_bill',0)}"
                                ).classes('text-gray-500')
                            with ui.row().classes('items-center gap-1'):
                                ui.label('Electric Bill :').classes('font-bold')
                                ui.label(f"₹ {bill.get('electric_bill',0)}").classes('text-gray-500')
                            with ui.row().classes('items-center gap-1'):
                                ui.label('Gas Bill :').classes('font-bold')
                                ui.label(f"₹ {bill.get('gas_bill',0)}"  ).classes('text-gray-500')
                            with ui.row().classes('items-center gap-1'):
                                ui.label('Other Charge :').classes('font-bold')
                                ui.label(f"₹ {bill.get('other_charge',0)}" ).classes('text-gray-500')
                            ui.separator()
                            ui.label(f"Total Charge : ₹ {bill.get('total_charge',0)}"  ).classes('text-orange-700 font-black text-lg')
                            with ui.row().classes('items-center gap-1'):
                                ui.label( 'Payment Status :'  ).classes(  'font-bold text-gray-900' )
                                status_val = bill.get('deposit_status', 'Not Initiated')
                                status_color = ( 'text-green-700'   if str(status_val).lower() == 'approved' else 'text-yellow-700')
                                ui.label(status_val).classes(f'{status_color} font-bold')
                            payment_status = bill.get('deposit_status')

                            if payment_status:
                                success_color = ( 'text-green-700' if str(payment_status).lower() == 'approved' else 'text-yellow-700')
                                success_text = ( 'SUCCESSFUL'  if str(payment_status).lower() == 'approved' else 'SUBMITTED' )
                                with ui.card().classes('w-full mt-4 bg-yellow-50 border border-yellow-300' ):
                                    ui.label( success_text ).classes(  f'{success_color} font-black text-center text-lg')
                            else:
                                ui.button('PROCEED',  on_click=proceed_payment  ).classes(  'w-full mt-4 bg-green-700 text-white font-bold' )
            if (state.current_page == "dashboard" 
                and state.renter_id
                and not state.active_renter_head_id):
                with ui.card().classes('p-6 w-full max-w-md mx-auto mt-10'):
                   ui.label('Please Create Head Of Family First').classes('text-red-700 font-bold text-center')
                   ui.button('Create Head Of Family',
                        on_click=lambda: (setattr(state,'current_page','profile'), setattr(state,'member_view','add'),
                            main_content.refresh())).classes('bg-green-700 text-white w-full mt-3')
                return
            elif state.is_logged_in and state.current_page == "dashboard":
                head_name = "Resident"
                try:
                    members = supabase.table('public_members').select('name,relation').eq( 'renter_id',   state.renter_id).execute()
                    if members.data:
                        for m in members.data:
                            if str(  m.get('relation', '') ).strip().lower() == 'head':
                                head_name = m.get(   'name', 'Resident'  )
                                break
                except Exception as ex:
                    print(ex)
                ui.label( f'Welcome {head_name} Dashboard').classes( 'w-full px-4 text-2xl font-bold text-green-900 mb-4 text-center')
                tiles = [
                 ('person', 'Member Detail', True),
                    ('bolt', 'Electric Bill', electric_enabled),
                    ('local_fire_department', 'Gas Bill', gas_enabled),
                    ('receipt_long', 'Rent Ledger', True),
                    ('payments', 'Pay Now', True),
                ]
                with ui.row().classes('w-full justify-center gap-3 px-2'):
                    for icon, label, enabled in tiles:
                        card = ui.card().classes(  'p-3 items-center w-36 shadow-sm border' )
                        if enabled:
                            card.classes( 'cursor-pointer hover:bg-green-50' ).on( 'click',  lambda l=label: open_page(l) )
                        else:
                            card.classes( 'opacity-30'  )
                        with card:
                            ui.icon(   icon,  size='2.2rem' ).classes(  'text-green-700' )
                            ui.label(   label ).classes( 'font-bold text-center mt-1 text-xs text-gray-700')
        main_content()
@ui.page('/meter')
def meter_page():
           
            token = ui.context.client.request.query_params.get('token')
            bill_type = ui.context.client.request.query_params.get('type')

            if not token or not bill_type:
                ui.label('Invalid QR')
                return

            # Step 1 : Token se room nikalo
            room_lookup = supabase.table('renters').select( 'room_no').eq(  'qr_token', token).limit(1).execute()
            if not room_lookup.data:
                ui.label('Invalid QR')
                return
            room_no = room_lookup.data[0]['room_no']
            # Step 2 : Us room ka ACTIVE renter nikalo
            active_renter = supabase.table(  'renters').select('*').eq( 'room_no',   room_no).eq(   'status',  'ACTIVE').limit(1).execute()

            if not active_renter.data:
                ui.label('No Active Renter Found')
                return
            renter_row = active_renter.data[0]
            renter_id = renter_row['id']
            head_id = renter_row['head_member_id']
         
            head_name = 'Unknown'

            head = supabase.table(
                'public_members'
            ).select(
                'name'
            ).eq(
                'id',
                head_id
            ).limit(1).execute()

            if head.data:
                head_name = head.data[0]['name']

            
            today = datetime.now()

            if today.day <= 5:
                prev_month_idx = (
                    today.month - 1
                    if today.month > 1
                    else 12
                )
                month_name = datetime(
                    today.year,
                    prev_month_idx,
                    1
                ).strftime('%B')
            else:
                month_name = today.strftime('%B')
            year_no = datetime.now().year

            ui.label(  f'{bill_type} Meter Reading').classes(   'text-2xl font-bold text-green-800')
            ui.separator()
            with ui.card().classes(
                'w-full max-w-xl mx-auto p-4 shadow-lg rounded-xl border'
            ):
                ui.label(f'{bill_type} Meter Reading') \
                    .classes('text-xl font-bold text-green-800 text-center w-full mb-3')

                with ui.grid(columns=2).classes(
                    'w-full gap-4 text-sm'
                ):

                    with ui.column().classes('gap-0'):
                        ui.label('Room No').classes(
                            'text-gray-500 text-xs font-bold'
                        )
                        ui.label(str(room_no)).classes(
                            'text-lg font-bold text-gray-800'
                        )

                    with ui.column().classes('gap-0'):
                        ui.label('Head Name').classes(
                            'text-gray-500 text-xs font-bold'
                        )
                        ui.label(head_name).classes(
                            'text-lg font-bold text-gray-800'
                        )

                    with ui.column().classes('gap-0'):
                        ui.label('Month').classes(
                            'text-gray-500 text-xs font-bold'
                        )
                        ui.label(month_name).classes(
                            'text-lg font-semibold text-blue-700'
                        )

                    with ui.column().classes('gap-0'):
                        ui.label('Year').classes(
                            'text-gray-500 text-xs font-bold'
                        )
                        ui.label(str(year_no)).classes(
                            'text-lg font-semibold text-blue-700'
                        )



                ui.separator()

                # --- 1. CHECK IF BILL ALREADY EXISTS ---
                existing_bill = supabase.table('utility_billing_ledger') \
                    .select('*') \
                    .eq('renter_id', renter_id) \
                    .eq('bill_type', bill_type) \
                    .eq('bill_month', month_name) \
                    .eq('bill_year', year_no) \
                    .execute()

                prev_reading = 0

                if existing_bill.data:

                    bill_data = existing_bill.data[0]
                    prev_reading = bill_data.get('prev_reading', 0)
                    ui.label( f"Previous Reading : {prev_reading} KWh").classes( 'text-orange-700 font-bold')
                else:

                    last_bill = supabase.table(
                        'utility_billing_ledger'
                    ).select('*') \
                    .eq('room_no', room_no) \
                    .eq('bill_type', bill_type) \
                    .order('bill_year', desc=True) \
                    .order('created_at', desc=True) \
                    .limit(1) \
                    .execute()

                    if last_bill.data:prev_reading = (last_bill.data[0].get('curr_reading',0) or 0)
                    ui.label(f"Previous Reading : {prev_reading} KWh").classes('text-orange-700 font-bold')  
                if existing_bill.data:
                    bill_data = existing_bill.data[0]
                    prev_reading = bill_data.get('prev_reading', 0)
                    curr_reading = bill_data.get('curr_reading', 0)
                    with ui.card().classes('w-full mt-4 p-4 bg-green-50 border border-green-200'):
                        ui.label('✅ Already Submitted').classes('text-green-800 font-bold text-center w-full text-lg')
                        with ui.row().classes('w-full justify-between mt-2'):
                            ui.label(f"Prev: {bill_data.get('prev_reading')} KWh").classes('text-gray-700 font-bold')
                            ui.label(f"Curr: {bill_data.get('curr_reading')} KWh").classes('text-green-700 font-bold')
                       
                        if bill_data.get('bill_img_url'):
                            ui.image(bill_data['bill_img_url']).classes('w-full mt-2 rounded-lg border')
                else:
                    # --- 2. AGAR BILL NAHI HAI, TOH CAMERA AUR INPUT DIKHAYEIN ---
                    if 'photo_url' not in app.storage.user:
                        app.storage.user['photo_url'] = None
                    if 'is_preview' not in app.storage.user:
                        app.storage.user['is_preview'] = False

                    reading_input = ui.input('Enter Current Reading').props('outlined dense type="number"').classes('w-full mt-2')

                    # Camera script (wahi purani)
                    ui.add_head_html('''
                        <script>
                            async function startCamera() {
                                const video = document.getElementById("video");
                                if (!video) return;
                                try {
                                    const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: "environment"}});
                                    video.srcObject = stream;
                                    video.play();
                                } catch (err) { console.error("Camera error:", err); }
                            }
                        </script>
                    ''')
                    ui.run_javascript('startCamera();')

                    async def capture_photo():
                        image_data = await ui.run_javascript('''
                            const video = document.getElementById("video");
                            const canvas = document.getElementById("canvas");
                            canvas.width = video.videoWidth;
                            canvas.height = video.videoHeight;
                            canvas.getContext("2d").drawImage(video, 0, 0);
                            return canvas.toDataURL("image/jpeg");
                        ''')
                        app.storage.user['photo_url'] = image_data
                        app.storage.user['is_preview'] = True
                        ui.update()

                    def submit_meter():
                        photo = app.storage.user.get('photo_url')
                        curr_input = reading_input.value
                        if not photo or not reading_input.value:
                            ui.notify('Fill details!', type='warning')
                            return

                        try:
                            curr_val = float(curr_input)
                            prev_val = float(prev_reading)

                            if curr_val < prev_val:
                                ui.notify(
                                    f'Current Reading ({curr_val}) cannot be less than Previous Reading ({prev_val})',
                                    type='negative'
                                )
                                return

                        except:
                            ui.notify('Invalid Reading', type='negative')
                            return


                        payload = {
                            'renter_id': renter_id, 'room_no': room_no, 'head_id': head_id,
                            'bill_type': bill_type, 'bill_month': month_name, 'bill_year': year_no,
                            'prev_reading': prev_val, 'curr_reading': curr_val,
                            'curr_reading_date': datetime.now().strftime('%Y-%m-%d'),
                            'bill_img_url': photo, 'status': 'Submitted'
                        }
                        supabase.table('utility_billing_ledger').insert(payload).execute()
                        ui.notify('Submitted!', type='positive')
                        ui.navigate.reload() # Page reload taaki summary dikhe

                    with ui.column().classes('w-full mt-4'):
                        with ui.element('div').bind_visibility_from(app.storage.user, 'is_preview', backward=lambda x: not x):
                            ui.html('<video id="video" autoplay playsinline muted style="width:100%; height:300px; object-fit:cover; background:black; border-radius:12px;"></video>')
                            ui.html('<canvas id="canvas" style="display:none"></canvas>')
                            ui.button('📷 Capture', on_click=capture_photo).classes('w-full mt-2 bg-blue-600 text-white')
                        
                        with ui.element('div').bind_visibility_from(app.storage.user, 'is_preview'):
                            ui.image().bind_source_from(app.storage.user, 'photo_url').classes('w-full rounded-lg border')
                            ui.button('🔄 Recapture', on_click=lambda: (app.storage.user.update({'is_preview': False}), ui.update())).classes('w-full mt-2 bg-orange-600 text-white')

                    ui.button('SUBMIT', on_click=submit_meter).classes('w-full mt-4 bg-green-700 text-white h-12 text-lg')
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='Meena Residency Portal', port=8080, host='0.0.0.0', storage_secret='meena_secret_999')
