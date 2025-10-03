use proc_macro::TokenStream;
use proc_macro2::TokenStream as TokenStream2;
use quote::{format_ident, quote};
use serde::Deserialize;
use std::{env, fs, path::PathBuf, sync::OnceLock};
use syn::{
    parse::Parse, parse::Parser, parse_macro_input, parse_quote, punctuated::Punctuated,
    token::Comma, Attribute, Expr, ExprCall, ExprStruct, Field, FieldValue, Fields, FnArg,
    ImplItem, ImplItemFn, ItemFn, ItemImpl, ItemStruct, Pat, PatIdent,
};

#[derive(Debug, Clone, Deserialize)]
struct RawFieldConfig {
    field: Vec<RawField>,
}

#[derive(Debug, Clone, Deserialize)]
struct RawField {
    ident: String,
    #[serde(rename = "type")]
    field_type: String,
    doc: Option<String>,
    default: Option<String>,
    precision: Option<String>,
}

#[derive(Debug, Clone)]
struct FieldSpec {
    ident: String,
    field_type: FieldType,
    doc: Option<String>,
    default: Option<String>,
    precision: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FieldType {
    Quantity,
    Price,
    U64,
    Bool,
}

static FIELD_SPECS: OnceLock<Vec<FieldSpec>> = OnceLock::new();

fn field_specs() -> &'static [FieldSpec] {
    FIELD_SPECS.get_or_init(load_field_specs).as_slice()
}

fn load_field_specs() -> Vec<FieldSpec> {
    let config_path = locate_config();
    let raw = fs::read_to_string(&config_path)
        .unwrap_or_else(|err| panic!("Failed to read {}: {err}", config_path.display()));
    let parsed: RawFieldConfig = toml::from_str(&raw)
        .unwrap_or_else(|err| panic!("Failed to parse {}: {err}", config_path.display()));

    parsed.field.into_iter().map(FieldSpec::from_raw).collect()
}

fn locate_config() -> PathBuf {
    if let Ok(path) = env::var("EXTENDED_BAR_CONFIG_PATH") {
        return PathBuf::from(path);
    }

    if let Ok(workspace_dir) = env::var("CARGO_WORKSPACE_DIR") {
        let candidate = PathBuf::from(workspace_dir).join("configs/extended_bar_fields.toml");
        if candidate.exists() {
            return candidate;
        }
    }

    let manifest_dir =
        env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR not set for extended bar macros");
    let mut current = PathBuf::from(manifest_dir);
    loop {
        let candidate = current.join("configs/extended_bar_fields.toml");
        if candidate.exists() {
            return candidate;
        }
        if !current.pop() {
            break;
        }
    }

    panic!(
        "Failed to locate configs/extended_bar_fields.toml. Set EXTENDED_BAR_CONFIG_PATH explicitly."
    );
}

impl FieldSpec {
    fn from_raw(raw: RawField) -> Self {
        Self {
            field_type: FieldType::from_label(&raw.field_type, &raw.ident),
            ident: raw.ident,
            doc: raw.doc,
            default: raw.default,
            precision: raw.precision,
        }
    }

    fn ident(&self) -> proc_macro2::Ident {
        format_ident!("{}", self.ident)
    }

    fn ident_str(&self) -> &str {
        &self.ident
    }

    fn ty_tokens(&self) -> TokenStream2 {
        match self.field_type {
            FieldType::Quantity => quote!(::nautilus_model::types::Quantity),
            FieldType::Price => quote!(::nautilus_model::types::Price),
            FieldType::U64 => quote!(u64),
            FieldType::Bool => quote!(bool),
        }
    }

    fn default_tokens(&self) -> TokenStream2 {
        let ident = &self.ident;
        match self.field_type {
            FieldType::Quantity => {
                let default_literal = self.default.as_deref().unwrap_or("0");
                let err_msg = format!(
                    "invalid default for extended field '{ident}': {{}}",
                    ident = ident
                );
                quote! {
                    <::nautilus_model::types::Quantity as ::std::str::FromStr>::from_str(#default_literal)
                        .unwrap_or_else(|err| panic!(#err_msg, err))
                }
            }
            FieldType::Price => {
                let default_literal = self.default.as_deref().unwrap_or("0");
                let err_msg = format!(
                    "invalid default for extended field '{ident}': {{}}",
                    ident = ident
                );
                quote! {
                    <::nautilus_model::types::Price as ::std::str::FromStr>::from_str(#default_literal)
                        .unwrap_or_else(|err| panic!(#err_msg, err))
                }
            }
            FieldType::U64 => {
                let parsed: u64 = self
                    .default
                    .as_deref()
                    .unwrap_or("0")
                    .parse::<u64>()
                    .unwrap_or_else(|err| {
                        panic!(
                            "invalid default for extended field '{ident}' as u64: {err}",
                            ident = ident,
                        )
                    });
                quote!(#parsed)
            }
            FieldType::Bool => {
                let parsed: bool = self
                    .default
                    .as_deref()
                    .unwrap_or("false")
                    .parse::<bool>()
                    .unwrap_or_else(|err| {
                        panic!(
                            "invalid default for extended field '{ident}' as bool: {err}",
                            ident = ident,
                        )
                    });
                quote!(#parsed)
            }
        }
    }
}

impl FieldType {
    fn from_label(label: &str, ident: &str) -> Self {
        match label {
            "quantity" => Self::Quantity,
            "price" => Self::Price,
            "u64" => Self::U64,
            "bool" => Self::Bool,
            other => panic!("Unsupported extended bar field type '{other}' for '{ident}'"),
        }
    }
}

fn extended_field_attributes(spec: &FieldSpec) -> Vec<Attribute> {
    let mut attrs = Vec::new();
    if let Some(doc) = &spec.doc {
        attrs.push(parse_quote!(#[doc = #doc]));
    }
    attrs
}

fn push_extended_struct_fields(fields: &mut Punctuated<Field, Comma>) {
    for spec in field_specs() {
        let ident = spec.ident();
        let ty = spec.ty_tokens();
        let mut field: Field = parse_quote!(pub #ident: #ty);
        field.attrs.extend(extended_field_attributes(spec));
        fields.push(field);
    }
}

fn append_extended_params(inputs: &mut Punctuated<FnArg, Comma>) {
    for spec in field_specs() {
        let ident = spec.ident();
        let ty = spec.ty_tokens();
        let arg: FnArg = parse_quote!(#ident: #ty);
        inputs.push(arg);
    }
}

fn append_struct_initializers(struct_expr: &mut ExprStruct) {
    for spec in field_specs() {
        let ident = spec.ident();
        let field_value: FieldValue = parse_quote!(#ident: #ident);
        struct_expr.fields.push(field_value);
    }
}

fn append_forward_arguments(call: &mut ExprCall) {
    for spec in field_specs() {
        let ident = spec.ident();
        call.args.push(parse_quote!(#ident));
    }
}

fn append_extended_py_params(inputs: &mut Punctuated<FnArg, Comma>) {
    for spec in field_specs() {
        let ident = spec.ident();
        let ty = spec.ty_tokens();
        let arg: FnArg = parse_quote!(#ident: ::core::option::Option<#ty>);
        inputs.push(arg);
    }
}

fn append_py_defaults(call: &mut ExprCall) {
    for spec in field_specs() {
        let ident = spec.ident();
        let default_expr = spec.default_tokens();
        call.args
            .push(parse_quote!(#ident.unwrap_or(#default_expr)));
    }
}

fn collect_arg_idents(inputs: &Punctuated<FnArg, Comma>, count: usize) -> Vec<proc_macro2::Ident> {
    inputs
        .iter()
        .take(count)
        .filter_map(|arg| match arg {
            FnArg::Typed(pat_type) => match &*pat_type.pat {
                Pat::Ident(PatIdent { ident, .. }) => Some(ident.clone()),
                _ => None,
            },
            FnArg::Receiver(_) => None,
        })
        .collect()
}

fn rewrite_py_new(fn_item: &mut ImplItemFn) -> syn::Result<()> {
    let specs = field_specs();
    if specs.is_empty() {
        return Ok(());
    }

    let original_param_len = fn_item.sig.inputs.len();
    append_extended_py_params(&mut fn_item.sig.inputs);

    let orig_args = collect_arg_idents(&fn_item.sig.inputs, original_param_len);
    let ext_idents: Vec<_> = specs.iter().map(|spec| spec.ident()).collect();

    if !ext_idents.is_empty() {
        let signature_attr: Attribute = parse_quote!(
            #[pyo3(signature = (#(#orig_args),*, *, #(#ext_idents = None),*))]
        );
        fn_item.attrs.push(signature_attr);
    }

    if let Some(stmt) = fn_item.block.stmts.last_mut() {
        match stmt {
            syn::Stmt::Expr(Expr::MethodCall(method_call), _) => {
                if let Expr::Call(call) = method_call.receiver.as_mut() {
                    append_py_defaults(call);
                } else {
                    return Err(syn::Error::new_spanned(
                        quote!(#method_call.receiver),
                        "extended_bar_pymethods_impl expects receiver to be Self::new_checked(...)",
                    ));
                }
            }
            _ => {
                return Err(syn::Error::new_spanned(
                    quote!(#stmt),
                    "extended_bar_pymethods_impl expects final expression to call a method on Self::new_checked(...)",
                ));
            }
        }
    } else {
        return Err(syn::Error::new_spanned(
            quote!(#fn_item),
            "extended_bar_pymethods_impl expects a non-empty function body",
        ));
    }

    Ok(())
}

#[proc_macro_attribute]
pub fn extended_bar_pymethods_impl(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut impl_block = parse_macro_input!(item as ItemImpl);

    for impl_item in &mut impl_block.items {
        if let ImplItem::Fn(method) = impl_item {
            if method.sig.ident == "py_new" {
                if let Err(error) = rewrite_py_new(method) {
                    return error.to_compile_error().into();
                }
            }
        }
    }

    quote!(#impl_block).into()
}

fn append_forward_arguments_expr(expr: &mut Expr) {
    match expr {
        Expr::Call(call) => {
            append_forward_arguments(call);
        }
        Expr::Return(ret) => {
            if let Some(inner) = ret.expr.as_mut() {
                append_forward_arguments_expr(inner);
            } else {
                panic!("extended_bar_ffi_new expects return Bar::new(...)");
            }
        }
        Expr::Block(block) => {
            if let Some(stmt) = block.block.stmts.last_mut() {
                ensure_bar_new_stmt(stmt);
            } else {
                panic!("extended_bar_ffi_new expects block ending with Bar::new(...)");
            }
        }
        Expr::Paren(paren) => {
            append_forward_arguments_expr(&mut paren.expr);
        }
        _ => {
            panic!("extended_bar_ffi_new expects final expression to be Bar::new(...)");
        }
    }
}

fn ensure_bar_new_stmt(stmt: &mut syn::Stmt) {
    match stmt {
        syn::Stmt::Expr(expr, _) => {
            append_forward_arguments_expr(expr);
        }
        _ => panic!("extended_bar_ffi_new expects final statement to be Bar::new(...)"),
    }
}

#[proc_macro_attribute]
pub fn extended_bar_struct(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut item_struct = parse_macro_input!(item as ItemStruct);

    match &mut item_struct.fields {
        Fields::Named(named) => {
            push_extended_struct_fields(&mut named.named);
        }
        _ => panic!("extended_bar_struct expects a struct with named fields"),
    }

    TokenStream::from(quote!(#item_struct))
}

#[proc_macro_attribute]
pub fn extended_bar_new_checked(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut func = parse_macro_input!(item as ItemFn);
    append_extended_params(&mut func.sig.inputs);

    if let Some(stmt) = func.block.stmts.last_mut() {
        match stmt {
            syn::Stmt::Expr(Expr::Call(call), _) => {
                if let Some(first_arg) = call.args.iter_mut().next() {
                    if let Expr::Struct(struct_expr) = first_arg {
                        append_struct_initializers(struct_expr);
                    } else {
                        panic!(
                            "extended_bar_new_checked expects Ok(Self {{ .. }}) as final expression"
                        );
                    }
                }
            }
            _ => {
                panic!("extended_bar_new_checked expects final expression to be Ok(Self {{ .. }})")
            }
        }
    }

    TokenStream::from(quote!(#func))
}

#[proc_macro_attribute]
pub fn extended_bar_new(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut func = parse_macro_input!(item as ItemFn);
    append_extended_params(&mut func.sig.inputs);

    if let Some(stmt) = func.block.stmts.last_mut() {
        match stmt {
            syn::Stmt::Expr(Expr::MethodCall(method_call), _) => {
                if let Expr::Call(call) = method_call.receiver.as_mut() {
                    append_forward_arguments(call);
                } else {
                    panic!("extended_bar_new expects final expression to call new_checked");
                }
            }
            _ => panic!("extended_bar_new expects final expression to call new_checked"),
        }
    }

    TokenStream::from(quote!(#func))
}

#[proc_macro_attribute]
pub fn extended_bar_ffi_new(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut func = parse_macro_input!(item as ItemFn);
    append_extended_params(&mut func.sig.inputs);

    if let Some(stmt) = func.block.stmts.last_mut() {
        ensure_bar_new_stmt(stmt);
    } else {
        panic!("extended_bar_ffi_new expects function body ending with Bar::new(...)");
    }

    TokenStream::from(quote!(#func))
}

#[proc_macro_attribute]
pub fn extended_bar_py_new(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut func = parse_macro_input!(item as ItemFn);
    append_extended_py_params(&mut func.sig.inputs);

    if let Some(stmt) = func.block.stmts.last_mut() {
        match stmt {
            syn::Stmt::Expr(Expr::MethodCall(method_call), _) => {
                if let Expr::Call(call) = method_call.receiver.as_mut() {
                    append_py_defaults(call);
                } else {
                    return syn::Error::new_spanned(
                        quote!(#method_call.receiver),
                        "extended_bar_py_new expects receiver to be Self::new_checked(...)",
                    )
                    .to_compile_error()
                    .into();
                }
            }
            _ => {
                return syn::Error::new_spanned(
                    quote!(#stmt),
                    "extended_bar_py_new expects final expression to call a method on Self::new_checked(...)",
                )
                .to_compile_error()
                .into();
            }
        }
    } else {
        return syn::Error::new_spanned(
            quote!(#func),
            "extended_bar_py_new expects a non-empty function body",
        )
        .to_compile_error()
        .into();
    }

    TokenStream::from(quote!(#func))
}

#[proc_macro]
pub fn constructor_defaults(_input: TokenStream) -> TokenStream {
    let defaults = field_specs().iter().map(|spec| {
        let value = spec.default_tokens();
        quote! { #value, }
    });

    TokenStream::from(quote! { #(#defaults)* })
}

#[proc_macro]
pub fn struct_defaults(_input: TokenStream) -> TokenStream {
    let defaults = field_specs().iter().map(|spec| {
        let ident = spec.ident();
        let value = spec.default_tokens();
        quote! { #ident: #value, }
    });

    TokenStream::from(quote! { #(#defaults)* })
}

struct TwoExprs {
    first: Expr,
    second: Expr,
}

impl Parse for TwoExprs {
    fn parse(input: syn::parse::ParseStream<'_>) -> syn::Result<Self> {
        let mut exprs = Punctuated::<Expr, Comma>::parse_separated_nonempty(input)?;
        if exprs.len() != 2 {
            return Err(syn::Error::new_spanned(
                quote!(#exprs),
                "expected exactly two comma-separated expressions",
            ));
        }
        let second = exprs.pop().unwrap().into_value();
        let first = exprs.pop().unwrap().into_value();
        Ok(Self { first, second })
    }
}

struct ThreeExprs {
    first: Expr,
    second: Expr,
    third: Expr,
}

impl Parse for ThreeExprs {
    fn parse(input: syn::parse::ParseStream<'_>) -> syn::Result<Self> {
        let mut exprs = Punctuated::<Expr, Comma>::parse_separated_nonempty(input)?;
        if exprs.len() != 3 {
            return Err(syn::Error::new_spanned(
                quote!(#exprs),
                "expected exactly three comma-separated expressions",
            ));
        }
        let third = exprs.pop().unwrap().into_value();
        let second = exprs.pop().unwrap().into_value();
        let first = exprs.pop().unwrap().into_value();
        Ok(Self {
            first,
            second,
            third,
        })
    }
}

fn get_by_name_macro_impl(input: TokenStream, field_type: FieldType) -> TokenStream {
    let args = parse_macro_input!(input as TwoExprs);
    let bar = args.first;
    let name = args.second;

    let arms = field_specs().iter().filter_map(|spec| {
        if spec.field_type == field_type {
            let ident = spec.ident();
            let name_str = spec.ident_str();
            Some(quote!(#name_str => Some(#bar.#ident),))
        } else {
            None
        }
    });

    TokenStream::from(quote! {{
        #[allow(unreachable_patterns)]
        match #name {
            #(#arms)*
            _ => None,
        }
    }})
}

#[proc_macro]
pub fn quantity_get_by_name(input: TokenStream) -> TokenStream {
    get_by_name_macro_impl(input, FieldType::Quantity)
}

#[proc_macro]
pub fn price_get_by_name(input: TokenStream) -> TokenStream {
    get_by_name_macro_impl(input, FieldType::Price)
}

#[proc_macro]
pub fn u64_get_by_name(input: TokenStream) -> TokenStream {
    get_by_name_macro_impl(input, FieldType::U64)
}

#[proc_macro]
pub fn bool_get_by_name(input: TokenStream) -> TokenStream {
    get_by_name_macro_impl(input, FieldType::Bool)
}

fn set_by_name_macro_impl(input: TokenStream, field_type: FieldType) -> TokenStream {
    let args = parse_macro_input!(input as ThreeExprs);
    let bar = args.first;
    let name = args.second;
    let value = args.third;

    let arms = field_specs().iter().filter_map(|spec| {
        if spec.field_type == field_type {
            let ident = spec.ident();
            let name_str = spec.ident_str();
            Some(quote!(#name_str => {
                #bar.#ident = #value;
                true
            },))
        } else {
            None
        }
    });

    TokenStream::from(quote! {{
        #[allow(unreachable_patterns)]
        match #name {
            #(#arms)*
            _ => false,
        }
    }})
}

#[proc_macro]
pub fn quantity_set_by_name(input: TokenStream) -> TokenStream {
    set_by_name_macro_impl(input, FieldType::Quantity)
}

#[proc_macro]
pub fn price_set_by_name(input: TokenStream) -> TokenStream {
    set_by_name_macro_impl(input, FieldType::Price)
}

#[proc_macro]
pub fn u64_set_by_name(input: TokenStream) -> TokenStream {
    set_by_name_macro_impl(input, FieldType::U64)
}

#[proc_macro]
pub fn bool_set_by_name(input: TokenStream) -> TokenStream {
    set_by_name_macro_impl(input, FieldType::Bool)
}

fn parse_defaults_as_exprs() -> Vec<Expr> {
    field_specs()
        .iter()
        .map(|spec| syn::parse2::<Expr>(spec.default_tokens()).expect("invalid default expression"))
        .collect()
}

fn parse_args_with_len(
    input: TokenStream,
    macro_name: &str,
    expected_len: usize,
) -> std::result::Result<Vec<Expr>, TokenStream> {
    let tokens = TokenStream2::from(input.clone());
    match Punctuated::<Expr, Comma>::parse_terminated.parse(input) {
        Ok(args) => {
            let vec: Vec<Expr> = args.into_iter().collect();
            if vec.len() != expected_len {
                Err(syn::Error::new_spanned(
                    tokens,
                    format!(
                        "{macro_name}! expects {expected_len} arguments, got {}",
                        vec.len()
                    ),
                )
                .to_compile_error()
                .into())
            } else {
                Ok(vec)
            }
        }
        Err(err) => Err(err.to_compile_error().into()),
    }
}

#[proc_macro]
pub fn bar_new_with_defaults(input: TokenStream) -> TokenStream {
    let base_args = match parse_args_with_len(input, "bar_new_with_defaults", 8) {
        Ok(args) => args,
        Err(err) => return err,
    };

    let defaults = parse_defaults_as_exprs();
    let base_args_ext = base_args.clone();

    TokenStream::from(quote! {{
        #[cfg(feature = "extended_bar")]
        {
            ::nautilus_model::data::bar::Bar::new(
                #(#base_args_ext),*
                #(, #defaults)*
            )
        }
        #[cfg(not(feature = "extended_bar"))]
        {
            ::nautilus_model::data::bar::Bar::new(
                #(#base_args),*
            )
        }
    }})
}

#[proc_macro]
pub fn bar_new_checked_with_defaults(input: TokenStream) -> TokenStream {
    let base_args = match parse_args_with_len(input, "bar_new_checked_with_defaults", 8) {
        Ok(args) => args,
        Err(err) => return err,
    };

    let defaults = parse_defaults_as_exprs();
    let base_args_ext = base_args.clone();

    TokenStream::from(quote! {{
        #[cfg(feature = "extended_bar")]
        {
            ::nautilus_model::data::bar::Bar::new_checked(
                #(#base_args_ext),*
                #(, #defaults)*
            )
        }
        #[cfg(not(feature = "extended_bar"))]
        {
            ::nautilus_model::data::bar::Bar::new_checked(
                #(#base_args),*
            )
        }
    }})
}

#[proc_macro]
pub fn bar_py_new_with_defaults(input: TokenStream) -> TokenStream {
    let base_args = match parse_args_with_len(input, "bar_py_new_with_defaults", 8) {
        Ok(args) => args,
        Err(err) => return err,
    };

    let base_args_ext = base_args.clone();
    let none_args = field_specs().iter().map(|_| quote!(None));

    TokenStream::from(quote! {{
        #[cfg(feature = "extended_bar")]
        {
            ::nautilus_model::data::bar::Bar::py_new(
                #(#base_args_ext),*
                #(, #none_args)*
            )
        }
        #[cfg(not(feature = "extended_bar"))]
        {
            ::nautilus_model::data::bar::Bar::py_new(
                #(#base_args),*
            )
        }
    }})
}
